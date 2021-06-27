# Binary Star Server
#
# Author: Dan Colish <dcolish@gmail.com>

from argparse import ArgumentParser
import time
from zhelpers import zmq
from collections import defaultdict
import json
import copy
import os
import sys
import subprocess

STATE_PRIMARY = 1
STATE_BACKUP = 2
STATE_ACTIVE = 3
STATE_PASSIVE = 4

PEER_PRIMARY = 1
PEER_BACKUP = 2
PEER_ACTIVE = 3
PEER_PASSIVE = 4
CLIENT_REQUEST = 5

HEARTBEAT = 1000

# store incoming messages from sensors according to their id
messages_to_acknowledge = defaultdict(dict)

# Store the responses to send to clients and clients acks
client_responses = {}
client_response_acks = {}
client_messages = []
server_sequence = 0


class BStarState(object):
    def __init__(self, state, event, peer_expiry):
        self.state = state
        self.event = event
        self.peer_expiry = peer_expiry


class BStarException(Exception):
    pass


fsm_states = {
    STATE_PRIMARY: {
        PEER_BACKUP: ("I: connected to backup (slave), ready as master",
                      STATE_ACTIVE),
        PEER_ACTIVE: ("I: connected to backup (master), ready as slave",
                      STATE_PASSIVE)
    },
    STATE_BACKUP: {
        PEER_ACTIVE: ("I: connected to primary (master), ready as slave",
                      STATE_PASSIVE),
        CLIENT_REQUEST: ("", False)
    },
    STATE_ACTIVE: {
        PEER_ACTIVE: ("E: fatal error - dual masters, aborting", False)
    },
    STATE_PASSIVE: {
        PEER_PRIMARY: ("I: primary (slave) is restarting, ready as master",
                       STATE_ACTIVE),
        PEER_BACKUP: ("I: backup (slave) is restarting, ready as master",
                      STATE_ACTIVE),
        PEER_PASSIVE: ("E: fatal error - dual slaves, aborting", False),
        CLIENT_REQUEST: (CLIENT_REQUEST, True)  # Say true, check peer later
    }
}


def run_fsm(fsm):
    # There are some transitional states we do not want to handle
    state_dict = fsm_states.get(fsm.state, {})
    res = state_dict.get(fsm.event)
    if res:
        msg, state = res
    else:
        return
    if state is False:
        raise BStarException(msg)
    elif msg == CLIENT_REQUEST:
        assert fsm.peer_expiry > 0
        if int(time.time() * 1000) > fsm.peer_expiry:
            fsm.state = STATE_ACTIVE
        else:
            raise BStarException()
    else:
        print(msg)
        fsm.state = state


###
#    Message Handler
#    - split message
#    - message syntax:
#        [ID, Sequence, MessageType, Value, Timestamp]
###
def handle_response(response):
    return response.decode("utf-8").split(',')


###
#    Handle Speed Messages
#    - create average speed server response
#    - average speeds within last 5 seconds
#    - update sequence hashmap
#    - create list of messages for particular client based of last ack
###
def sensor_response(message):
    if message[2] != 'Speed': return []
    client_messages.append(message)
    cur_time = int(time.time())
    global server_sequence

    # Start Tracking Acked sequence if message from new client
    if int(message[0]) not in client_response_acks:
        client_response_acks[int(message[0])] = server_sequence

    # pop messages older than 5 seconds
    while (cur_time - int(client_messages[0][4])) > 5:
        client_messages.pop(0)

    # Average Speed in last 5 minutes
    average_speed = int(sum([int(i[3]) for i in client_messages]) / len(client_messages))

    # Create new server message
    client_responses[server_sequence] = str(server_sequence) + ",Average," + str(average_speed) + "," + str(cur_time)
    server_sequence += 1

    # Create message queue for client
    # between clients last acked and current sequence
    to_send = [client_responses[i] for i in range(client_response_acks[int(message[0])] + 1, server_sequence)]
    return to_send


###
#    Handle 'Average' Message Acknowledgments
#    - update client ack dictionaries
#    - delete average message buffer based off lowest client ack
###
def handle_average_ack(message):
    client_response_acks[int(message[0])] = max(int(message[1]), client_response_acks[int(message[0])])
    for i in range(min(client_responses.keys()), min(client_response_acks.values())):
        del client_responses[i]


# Back up dictionary
def write_replica_dict(dict_type, read_dict):
    if dict_type == "client_responses":
        file_name = "replica_client_responses.json"
    else:
        file_name = "replica_client_response_acks.json"
    with open(file_name, "w") as outfile:
        json.dump(read_dict, outfile)


# Restore dictionary
def read_replica_dict(dict_type):
    # file_name = ""
    if dict_type == "client_responses":
        file_name = "replica_client_responses.json"
    else:
        file_name = "replica_client_response_acks.json"
    try:
        with open(file_name) as json_file:
            read_dict = json.load(json_file)
            read_dict = {int(k): v for k, v in read_dict.items()}
        return read_dict
    except IOError:
        return dict


# Back up list
def read_replica_list():
    try:
        with open('replica_messages.json') as json_file:
            read_list = json.load(json_file)
            return read_list
    except IOError:
        return []


# Restore list
def write_replica_list(read_list):
    with open('replica_messages.json', "w") as outfile:
        json.dump(read_list, outfile)


# Back up int
def read_replica_number():
    try:
        with open('replica_sequence.txt') as txt_file:
            read_number = int(txt_file.read())
            return read_number
    except IOError:
        return 0


# Restore int
def write_replica_number(read_number):
    with open('replica_sequence.txt', "w") as outfile:
        outfile.write(str(read_number))


def main():
    parser = ArgumentParser()
    group = parser.add_mutually_exclusive_group()
    group.add_argument("-p", "--primary", action="store_true", default=False)
    group.add_argument("-b", "--backup", action="store_true", default=False)
    args = parser.parse_args()

    ctx = zmq.Context()
    statepub = ctx.socket(zmq.PUB)
    statesub = ctx.socket(zmq.SUB)
    statesub.setsockopt_string(zmq.SUBSCRIBE, u"")
    frontend = ctx.socket(zmq.ROUTER)

    fsm = BStarState(0, 0, 0)

    # Store Primary/Backup status
    # Inherits it's logic from fsm class
    # 3 = connected to backup server, accepting client connections
    # 4 = connected to primary server, doesn't accept client connections
    server_status = 4

    # DECLARING GLOBAL VALUES, PREVENTS SHADOWING
    global client_responses
    global client_response_acks
    global client_messages
    global server_sequence

    peer_ip_remote = "192.168.1"
    peer_running_directory = "/root/"
    peer_username = "root"

    rsync_command = "rsync -avz replica_client_response_acks.json  replica_client_responses.json  " \
                    "replica_messages.json  replica_sequence.txt " + peer_username + "@" + peer_ip_remote + ":" + peer_running_directory

    if args.primary:
        print("I: Primary master, waiting for backup (slave)")
        frontend.bind("tcp://*:5001")
        statepub.bind("tcp://*:5003")
        statesub.connect("tcp://localhost:5004")
        fsm.state = STATE_PRIMARY
    elif args.backup:
        print("I: Backup slave, waiting for primary (master)")
        frontend.bind("tcp://*:5002")
        statepub.bind("tcp://*:5004")
        statesub.connect("tcp://localhost:5003")
        statesub.setsockopt_string(zmq.SUBSCRIBE, u"")
        fsm.state = STATE_BACKUP

    send_state_at = int(time.time() * 1000 + HEARTBEAT)
    poller = zmq.Poller()
    poller.register(frontend, zmq.POLLIN)
    poller.register(statesub, zmq.POLLIN)
    while True:
        time_left = send_state_at - int(time.time() * 1000)
        if time_left < 0:
            time_left = 0
        socks = dict(poller.poll(time_left))

        # READ REPLICAS IF IT FAILED OVER, RESTORE VALUES
        if server_status == 3 and fsm.state == 3:
            # RESTORE VALUES FROM PRIMARY
            client_responses = copy.deepcopy(read_replica_dict("client_responses"))
            client_response_acks = copy.deepcopy(read_replica_dict("client_response_acks"))
            client_messages = copy.deepcopy(read_replica_list())
            server_sequence = copy.deepcopy(read_replica_number())

            # Prevents overwriting replicated data
            server_status = 4

        if socks.get(frontend) == zmq.POLLIN:

            fsm.event = CLIENT_REQUEST
            msg = frontend.recv_multipart()
            print("I: client message (%s)" % msg)

            # Save the Socket Header for Later use
            msg_header = msg

            # parse and save message
            parsed_message = handle_response(msg[1])
            sensor_id = parsed_message[0]
            sequence = parsed_message[1]

            ## Handle 'Speed' and 'Average' message types
            if parsed_message[2] == 'Average':
                handle_average_ack(parsed_message)
                continue
            else:
                messages_to_acknowledge[sensor_id][sequence] = msg

            ## Create list of 'Average' Message types to send this client
            to_send = sensor_response(parsed_message)

            try:
                run_fsm(fsm)

                ## Send All Messages
                for seq, m in list(messages_to_acknowledge[sensor_id].items()):
                    frontend.send_multipart(m)
                    del messages_to_acknowledge[sensor_id][seq]

                for m in to_send:
                    msg_header[1] = bytes(m, "utf8")
                    frontend.send_multipart(msg_header)

            except BStarException:
                del msg

        # TRYING TO DETERMINE WHICH ONE IS BEHIND
        if fsm.state == 4:
            server_status = 3

        # BACKUP
        # Start backing up if the server is connected to a backup server and accepting client messages
        if server_status == 4 and fsm.state == 4:
            write_replica_dict("client_responses", client_responses)
            write_replica_dict("client_response_acks", client_response_acks)
            write_replica_list(client_messages)
            write_replica_number(server_sequence)
            # Send backed up data to replica
            os.system(rsync_command)

        if socks.get(statesub) == zmq.POLLIN:
            msg = statesub.recv()
            fsm.event = int(msg)
            del msg
            try:
                run_fsm(fsm)
                fsm.peer_expiry = int(time.time() * 1000) + (2 * HEARTBEAT)
            except BStarException:
                break
        if int(time.time() * 1000) >= send_state_at:
            statepub.send_string("%d" % fsm.state)
            send_state_at = int(time.time() * 1000) + HEARTBEAT


if __name__ == '__main__':
    main()
