from time import sleep
import time
import zmq
import random
import threading
from argparse import ArgumentParser
from zmq import ssh

REQUEST_TIMEOUT = 1000  # msecs

# dictionary to store unacknowledged messages
messages = {}
sequence = 0

###
#    Generate Message 
#    - random speed within 70 to 120 kph
#    - add timestamp
###
def message_generator():
    global messages, sequence

    while True:
        msg = "Speed," + str(random.randrange(70,120)) + "," + str(int(time.time()))
        messages[sequence] = msg
        sequence += 1
        sleep(1)

###
#    Handle 'Average' Message Acknowledgments
#    - update client ack dictionaries
#    - delete average message buffer based off lowest client ack
###
def handle_response(response):
    return response.decode("utf-8").split(',')

def main():

    # TODO: load previous state from file
    global messages

    # start message generator
    generator_thread = threading.Thread(target=message_generator)
    generator_thread.daemon=True
    generator_thread.start()

    # get sensor id
    parser = ArgumentParser()
    parser.add_argument("-id", "--id", type=int, default=1)
    parser.add_argument("-ip1", "--ip1", type=str, default="localhost")
    parser.add_argument("-ip2", "--ip2", type=str, default="localhost")
    args = parser.parse_args()

    # connect to server
    server = ['tcp://localhost:5001', 'tcp://localhost:5002']
    server_ips = [args.ip1, args.ip2]
    server_nbr = 0
    ctx = zmq.Context()
    client = ctx.socket(zmq.DEALER)
    #client.connect(server[server_nbr])
    ssh.tunnel_connection(client, server[server_nbr],'petbangert@{}'.format(server_ips[server_nbr]))
    poller = zmq.Poller()
    poller.register(client, zmq.POLLIN)

    # send / recieve loop
    while True:

        # print number of unsent messages
        print( "I: Number of unsent messages:", len(messages) )

        # send all unacknowledged messages
        for seq, msg in list(messages.items()):
            client.send_string("%s," % str(args.id) + "%s," % seq + "%s" % msg)

        # recieve loop
        msg_recieved = 0
        while True:
            socks = dict(poller.poll(REQUEST_TIMEOUT))
            if socks.get(client) == zmq.POLLIN:

                # check that at least one message was recieved
                msg_recieved += 1

                # recieve response
                msg = client.recv_multipart()
                reply = handle_response(msg[0])
                print("I: server replied OK (%s)" % reply)

                # message was delivered, delete from storage
                if reply[1] == 'Average':
                    client.send_string("%s," % str(args.id) + ",".join(reply))
                else:    
                    messages.pop(int(reply[1]), None)

            elif msg_recieved == 0: # we didn't recieve any messages, server may be down
                print("W: no response from server, failing over")
                poller.unregister(client)
                client.close()
                server_nbr = (server_nbr + 1) % len(server)
                print("I: Attempting to connect to server at %s.." % server[server_nbr])
                client = ctx.socket(zmq.DEALER)
                poller.register(client, zmq.POLLIN)
                # reconnect
                client.connect(server[server_nbr])
                break
            else: # no more messages available
                break


        # Sleep shortly when not sending to save CPU from Xploding
        sleep(0.25)

if __name__ == '__main__':
    main()
