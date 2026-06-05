---
language: c++
tags: [pattern, concurrency]
title: Multithreading
description: std::thread, std::async, std::mutex, std::lock_guard, std::condition_variable, std::future, std::promise.
source: pattern
---

```c++
#include <iostream>
#include <thread>
#include <mutex>
#include <condition_variable>
#include <future>
#include <vector>
#include <chrono>
#include <queue>

std::mutex cout_mutex;

// --- Basic thread with mutex ---
void worker(int id) {
    std::lock_guard<std::mutex> lock(cout_mutex);
    std::cout << "Worker " << id << " running on thread "
              << std::this_thread::get_id() << "\n";
}

// --- Thread-safe queue with condition_variable ---
template <typename T>
class ThreadSafeQueue {
    std::queue<T> queue_;
    mutable std::mutex mtx_;
    std::condition_variable cv_;
public:
    void push(T value) {
        std::lock_guard<std::mutex> lock(mtx_);
        queue_.push(std::move(value));
        cv_.notify_one();
    }

    T pop() {
        std::unique_lock<std::mutex> lock(mtx_);
        cv_.wait(lock, [this] { return !queue_.empty(); });
        T value = std::move(queue_.front());
        queue_.pop();
        return value;
    }
};

// --- Async / future / promise ---
int compute_square(int x) {
    std::this_thread::sleep_for(std::chrono::milliseconds(100));
    return x * x;
}

int main() {
    // --- Basic threads ---
    std::cout << "--- Basic threads ---\n";
    std::vector<std::thread> threads;
    for (int i = 0; i < 4; ++i)
        threads.emplace_back(worker, i);
    for (auto& t : threads) t.join();

    // --- Thread-safe queue with condition variable ---
    std::cout << "\n--- Thread-safe queue ---\n";
    ThreadSafeQueue<int> tsq;
    std::thread producer([&] {
        for (int i = 0; i < 5; ++i) {
            std::this_thread::sleep_for(std::chrono::milliseconds(50));
            tsq.push(i);
        }
    });
    std::thread consumer([&] {
        for (int i = 0; i < 5; ++i) {
            int val = tsq.pop();
            std::lock_guard<std::mutex> lock(cout_mutex);
            std::cout << "Consumed: " << val << "\n";
        }
    });
    producer.join();
    consumer.join();

    // --- Async + future ---
    std::cout << "\n--- Async / future ---\n";
    std::vector<std::future<int>> futures;
    for (int i = 1; i <= 4; ++i)
        futures.push_back(std::async(std::launch::async, compute_square, i));
    for (auto& f : futures)
        std::cout << "Result: " << f.get() << "\n";

    return 0;
}

```
