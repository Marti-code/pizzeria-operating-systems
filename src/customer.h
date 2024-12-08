#ifndef CUSTOMER_H
#define CUSTOMER_H

#include <vector>
#include <thread>

class Customer {
public:
    Customer(int groupSize);
    void orderPizza(); // Interact with the Cashier to place an order.
    void receivePizza(); // Wait for a short time (simulate pizza preparation) before receiving the pizza.
    void findSeating(); // Request a table from the Table Manager.
    void enjoyMeal(); // Simulate the time taken to eat.
    void leavePizzeria(); // Notify the system upon leaving.

    // one more function for responding to fire alarm - evacuate immediately

    // Getters and setters
    int getGroupSize();

private:
    int groupSize;
};

#endif
