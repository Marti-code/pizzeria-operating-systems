#include "customer.h"
#include "table_manager.h"
#include "cashier.h"
#include <iostream>

Customer::Customer(int size) : groupSize(size) {
    // Constructor implementation
}

void Customer::orderPizza() {
    // Interact with Cashier
}

void Customer::receivePizza() {
    // Simulate receiving pizza
}

void Customer::findSeating() {
    // Request seating from TableManager
}

void Customer::enjoyMeal() {
    // Simulate time taken to eat
}

void Customer::leavePizzeria() {
    // Update states and resources
}

int Customer::getGroupSize() {
    return groupSize;
}
