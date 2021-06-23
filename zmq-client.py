from time import sleep
import zmq
import time
import random
from argparse import ArgumentParser

REQUEST_TIMEOUT = 1000  # msecs
SETTLE_DELAY = 2000  # before failing over

def get_message():
    msg = ""
    #+ random.randrange(-3,3)
    if (int(time.time())+ random.randrange(-3,3))  % 10 == 0: 
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
    expect_reply = False

    sequence = 0
    while True:

        # Check if we send a message
        msg = get_message()
        if msg != "":
            client.send_string("%s," % str(args.id) + "%s," % sequence + "%s" % msg)
            expect_reply = True


        # Wait for response
        while expect_reply:
            socks = dict(poller.poll(REQUEST_TIMEOUT))
            if socks.get(client) == zmq.POLLIN:

                # Recieve Response
                reply = handle_response(client.recv())
                
                if int(reply[1]) == sequence:
                    print("I: server replied OK (%s)" % reply)
                    expect_reply = False
                    sequence += 1
                    sleep(1)
                else:
                    print("E: malformed reply from server: %s" % reply)
            else:
                print("W: no response from server, failing over")
                sleep(SETTLE_DELAY / 1000)
                poller.unregister(client)
                client.close()
                server_nbr = (server_nbr + 1) % 2
                print("I: connecting to server at %s.." % server[server_nbr])
                client = ctx.socket(zmq.REQ)
                poller.register(client, zmq.POLLIN)
                # reconnect and resend request
                client.connect(server[server_nbr])
                client.send_string("%s," % str(args.id) + "%s," % sequence + "%s" % msg)
        
        # Sleep shortly when not sending to save CPU from Xploding
        sleep(0.25)

if __name__ == '__main__':
    main()