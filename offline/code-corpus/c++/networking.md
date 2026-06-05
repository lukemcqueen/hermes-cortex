---
language: c++
tags: [pattern, networking]
title: Networking (Boost.Asio / C++20 std::net)
description: Boost.Asio basics: async TCP echo server/client, steady_timer, and error_code handling. Notes on C++23 std::net.
source: pattern
---

```c++
// Requires: Boost.Asio (libboost-dev) or standalone Asio
// Compile: g++ -std=c++20 -I/usr/include networking.cpp -lboost_system -lpthread
//
// If using standalone Asio: #define ASIO_STANDALONE
// If using C++23 std::net (experimental): #include <experimental/net>

#include <iostream>
#include <thread>
#include <string>

// --- Boost.Asio includes ---
#include <boost/asio.hpp>

using boost::asio::ip::tcp;

// ===================== ECHO SERVER =====================
// Session handler — runs in one thread per connection
class Session : public std::enable_shared_from_this<Session> {
    tcp::socket socket_;
    enum { max_length = 1024 };
    char data_[max_length];

public:
    explicit Session(tcp::socket socket)
        : socket_(std::move(socket)) {}

    void start() { do_read(); }

private:
    void do_read() {
        auto self = shared_from_this();
        socket_.async_read_some(
            boost::asio::buffer(data_, max_length),
            [this, self](boost::system::error_code ec, std::size_t length) {
                if (!ec) {
                    do_write(length);
                }
            });
    }

    void do_write(std::size_t length) {
        auto self = shared_from_this();
        boost::asio::async_write(
            socket_,
            boost::asio::buffer(data_, length),
            [this, self](boost::system::error_code ec, std::size_t /*length*/) {
                if (!ec) {
                    do_read();  // continue reading
                }
            });
    }
};

class Server {
    tcp::acceptor acceptor_;

public:
    Server(boost::asio::io_context& io, short port)
        : acceptor_(io, tcp::endpoint(tcp::v4(), port)) {
        do_accept();
        std::cout << "Echo server listening on port " << port << "\n";
    }

private:
    void do_accept() {
        acceptor_.async_accept(
            [this](boost::system::error_code ec, tcp::socket socket) {
                if (!ec) {
                    std::make_shared<Session>(std::move(socket))->start();
                }
                do_accept();  // accept next connection
            });
    }
};

// ===================== ECHO CLIENT =====================
void run_client(const std::string& host, short port) {
    try {
        boost::asio::io_context io;
        tcp::socket socket(io);
        tcp::resolver resolver(io);
        boost::asio::connect(socket, resolver.resolve(host, std::to_string(port)));

        std::string message = "Hello, Asio!";
        boost::asio::write(socket, boost::asio::buffer(message));

        char reply[1024];
        std::size_t len = socket.read_some(boost::asio::buffer(reply));
        std::cout << "Server echoed: " << std::string(reply, len) << "\n";

        socket.close();
    } catch (std::exception& e) {
        std::cerr << "Client error: " << e.what() << "\n";
    }
}

// ===================== TIMER EXAMPLE =====================
void timer_example(boost::asio::io_context& io) {
    auto timer = std::make_shared<boost::asio::steady_timer>(io);
    timer->expires_after(std::chrono::seconds(1));

    timer->async_wait([timer](boost::system::error_code ec) {
        if (!ec) {
            std::cout << "Timer fired after 1 second\n";
        }
    });
}

int main() {
    try {
        boost::asio::io_context io;

        Server server(io, 12345);

        // Start timer
        timer_example(io);

        // Run client in a separate thread
        std::thread client_thread([&] {
            std::this_thread::sleep_for(std::chrono::milliseconds(100));
            run_client("127.0.0.1", 12345);
        });

        // Run the I/O context (event loop)
        io.run();

        client_thread.join();
    } catch (std::exception& e) {
        std::cerr << "Fatal: " << e.what() << "\n";
        return 1;
    }

    return 0;
}

```
