# Fog Computing Prototyping Assignment

This repository contains a fog application that simulates an adaptive speed limit use-case to demonstrate reliable message delivery. It consists of a `zmq-client.py` script to simulate speed-limit sensors and a `zmq-server.py` script to simulate a processing component in the cloud. The [ZeroMQ](https://zeromq.org) messaging library is used to facilitate communication between components.

## Application description

The domain of this Proof of concept is an Autobahn sensor network, in which roadway sensors are reading the speed of passing cars, sending these readings to a centralized system. The centralized system will then aggregate these speed readings into an average speed within a 5 second window and respond to each client with the most recent average speeds. The idea being that this information can be used for setting adapative speed limits.



## Reliable message delivery

The client/server architecture combines multple strategies to ensure reliable message delivers

#### Acknowledgements

All communications originating from the client or server must be acknowledged by the recieving party. 

- The clients are responsible for generating `Speed` messages, which conatin the clients id, and a sequence number. The Server will respond with an acknowledgement to every message. The Client is responsible for buffering and resending unacknowledged messages.

- The servers generate `Average` speed messages to send to each client. The server retains a hasmap for each connected client and its last acknowledged sequence number and buffers all messages greater than the minimum client sequence. 

These mechanisms ensure reliable deliver of messages in continuous connectivity scenarios, the strategies below will describe how reliability is ensured in disconnection scenarios.


#### Server Side Avaliability:

 The Server architecture is based off the [Binary Star](https://zguide.zeromq.org/docs/chapter4/) example provided by zmq documentation. This server topology is effectively a Primary/Replica server setup, in which the client is designed to failover to the replica if a request timeout occurs on the primary server. 

#### Server Side Replication:

 On top of the Binary Star implementation we extended the functionality so that primary server is responsible for sending updates to the replica server so that in the case of a failover to the replica, unsent messages and sequence/acknowledgement states will be up to date providing transparent failover from the clients point of view.

 The replication is done by the primary writing its state to a file and rsyncing this information to the replicas working directory. This approach is inspired by the Write Ahead Log style backup that Postgres uses, or the Append only Log which Redis uses in which a Hard drive based backup can be replayed to recover the systems state in case of a complete downtime.

#### In Memory Message buffering

From the client side all unacknowledge messages are buffered in memory until sent and properly acknowledged from the server side. 

## Conclusion

With the combination of Acknowledgements, Primary/Replica avaliability and replication, and Message buffering the entire system is robust enough to effectively continuously serve its intended function with 2/4 systems enitrely crashed or disonnected. 

## Usage

Start the primary and backup cloud servers with the following commands:

`python3 zmq-server.py --primary`

`python3 zmq-server.py --backup`

Start sensors with the client script by passing a unique id:

`python3 zmq-client.py --id 1`

## Demo

A video demo can be seen in the `file_name` file.
