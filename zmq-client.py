from time import sleep
import zmq
import time
import random
from argparse import ArgumentParser

REQUEST_TIMEOUT = 1000  # msecs

# dictionary to store unacknowledged messages
messages = {}

def get_message():
    msg = ""
    #+ random.randrange(-3,3)
    #if (int(time.time())+ random.randrange(-3,3)) % 10 == 0:
    if (True):
        msg = "Speed : " + str(random.randrange(70,120))
    return msg

# Message syntax:
# ID, Sequence, Message
def handle_response(response):
    return response.decode("utf-8").split(',')

def main():
    parser = ArgumentParser()
    parser.add_argument("-id", "--id", type=int, default=1)
    args = parser.parse_args()

    server = ['tcp://localhost:5001', 'tcp://localhost:5002']
    server_nbr = 0
    ctx = zmq.Context()
    client = ctx.socket(zmq.REQ)
    client.connect(server[server_nbr])
    poller = zmq.Poller()
    poller.register(client, zmq.POLLIN)

    sequence = 0
    while True:

        # print number of unsent messages
        print( "I: Number of unsent messages:", len(messages) )

        # produce a new message
        msg = get_message()

        # save message to dictionary and send
        messages[sequence] = msg

        # TODO: send all unacknowledged messages
        client.send_string("%s," % str(args.id) + "%s," % sequence + "%s" % msg)
        sequence += 1

        # check if messages are available
        socks = dict(poller.poll(REQUEST_TIMEOUT))
        if socks.get(client) == zmq.POLLIN:

            # recieve response
            reply = handle_response(client.recv())
            print("I: server replied OK (%s)" % reply)

            # message was delivered, delete from queue
            del messages[int(reply[1])]
            sleep(1)

        else:
            print("W: no response from server, failing over")
            sleep(1)
            poller.unregister(client)
            client.close()
            server_nbr = (server_nbr + 1) % len(server)
            print("I: connecting to server at %s.." % server[server_nbr])
            client = ctx.socket(zmq.REQ)
            poller.register(client, zmq.POLLIN)
            # reconnect
            client.connect(server[server_nbr])

        # Sleep shortly when not sending to save CPU from Xploding
        sleep(0.25)

if __name__ == '__main__':
    main()
