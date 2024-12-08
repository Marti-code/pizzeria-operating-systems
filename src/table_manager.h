#ifndef TABLE_MANAGER_H
#define TABLE_MANAGER_H

#include <mutex>
#include <condition_variable>
#include <vector>

class TableManager {
public:
    TableManager(int x1, int x2, int x3, int x4);
    bool assignTable(int groupSize);
    void releaseTable(int tableSize);

private:
    std::mutex mtx;
    std::condition_variable cv;
    std::vector<int> tables;
};

#endif
