---
language: typescript
tags: [pattern, util]
title: Classes & Access Modifiers
description: public/private/protected, readonly, abstract class, implements interface.
source: reference
---

```typescript
// Interface for class contract
interface Drawable {
  draw(): void;
}

// Abstract class
abstract class Shape {
  constructor(protected readonly name: string) {}

  abstract area(): number;

  describe(): void {
    console.log(`Shape: ${this.name}, area: ${this.area()}`);
  }
}

// Class implementing interface and extending abstract class
class Circle extends Shape implements Drawable {
  // public (default), private, protected, readonly
  private _radius: number;

  constructor(name: string, radius: number) {
    super(name);
    this._radius = radius;
  }

  // Getter
  get radius(): number {
    return this._radius;
  }

  // Setter
  set radius(value: number) {
    if (value <= 0) throw new Error('Radius must be positive');
    this._radius = value;
  }

  // Abstract method implementation
  area(): number {
    return Math.PI * this._radius ** 2;
  }

  // Interface implementation
  draw(): void {
    console.log(`Drawing a circle with radius ${this._radius}`);
  }
}

const circle = new Circle('MyCircle', 5);
console.log(circle.area()); // ~78.54
circle.draw();
// circle._radius; // Error: private
// circle.name;    // Error: protected

```
