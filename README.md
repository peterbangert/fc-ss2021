# Fog Computing Prototyping Assignment

This repository contains a fog application that simulates an adaptive speed limit use-case to demonstrate reliable message delivery. It consists of a `zmq-client.py` script to simulate speed-limit sensors and a `zmq-server.py` script to simulate a processing component in the cloud. The [ZeroMQ](https://zeromq.org) messaging library is used to facilitate communication between components.

## Application description

In this proof of concept application, multiple traffic sensors measure the speed of vehicles along a strech of highway. Sensors transmit their measurments to a central server, which aggregates and calculates the average speed of all vehicles along the highway in the last five seconds. The results are then sent to each sensor, with the idea being that this information can be used for setting adapative speed limits.

## Reliable message delivery

The client and server handle reliable message delivery in slightly different ways.

Client-side:

Server-side:

## Usage

Start the primary and backup cloud servers with the following commands:

`python3 zmq-server.py --primary`

`python3 zmq-server.py --backup`

Start sensors with the client script by passing a unique id:

`python3 zmq-client.py --id 1`

## Demo

A video demo can be seen in the `file_name` file.
