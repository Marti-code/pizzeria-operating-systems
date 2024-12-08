#include <csignal>
#include <thread>
#include <chrono>
#include <cstdlib>

void firefighterRoutine() {
    // Wait for a random time
    std::this_thread::sleep_for(std::chrono::seconds(rand() % 30 + 30));
    // Send fire alarm signal, defined by me
    //std::raise(MYSIG);
}
