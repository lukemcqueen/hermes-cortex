---
language: javascript
tags: [pattern, util]
title: ES6 Classes
description: Class syntax: constructor, methods, getters/setters, static, extends, super.
source: textbook
---

```javascript
class Animal {
  constructor(name) {
    this.name = name;
  }

  speak() {
    return `${this.name} makes a sound.`;
  }

  static categorize() {
    return 'Living thing';
  }

  get info() {
    return `Name: ${this.name}`;
  }

  set alias(nick) {
    this.name = nick;
  }
}

class Dog extends Animal {
  constructor(name, breed) {
    super(name);
    this.breed = breed;
  }

  speak() {
    return `${this.name} barks!`;
  }

  static categorize() {
    return 'Mammal';
  }
}

const dog = new Dog('Rex', 'Husky');
console.log(dog.speak());
console.log(Dog.categorize());

```
