---
language: javascript
tags: [pattern]
title: Prototypes & Inheritance
description: Prototype chain, Object.create, constructor functions vs class syntax.
source: textbook
---

```javascript
// Constructor function
function Vehicle(type, speed) {
  this.type = type;
  this.speed = speed;
}

Vehicle.prototype.move = function() {
  return `${this.type} moves at ${this.speed} km/h`;
};

Vehicle.prototype.stop = function() {
  this.speed = 0;
  return `${this.type} stopped`;
};

// Prototypal inheritance
function Car(brand, speed) {
  Vehicle.call(this, 'car', speed);
  this.brand = brand;
}

Car.prototype = Object.create(Vehicle.prototype);
Car.prototype.constructor = Car;

Car.prototype.honk = function() {
  return `${this.brand} honks!`;
};

const tesla = new Car('Tesla', 120);
console.log(tesla.move());
console.log(tesla.honk());
console.log(tesla instanceof Vehicle);

// Object.create for direct inheritance
const proto = { greet() { return 'Hi!'; } };
const obj = Object.create(proto);
console.log(obj.greet()); // 'Hi!'

```
