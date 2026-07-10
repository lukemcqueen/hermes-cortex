---
language: csharp
tags: [csharp, testing, xunit, moq, fluentassertions, nunit]
title: Unit Testing (xUnit / NUnit)
description: xUnit [Fact] and [Theory] tests, Moq for mocking dependencies, FluentAssertions for readable assertions, and NUnit equivalent attributes.
source: pattern
---

```csharp
using Xunit;
using Moq;
using FluentAssertions;
using static FluentAssertions.FluentActions;

// ── System under test ──────────────────────────────────────────────────
public interface IPriceService { decimal GetDiscount(string customerId); }
public class OrderCalculator
{
    private readonly IPriceService _prices;
    public OrderCalculator(IPriceService prices) => _prices = prices;

    public decimal CalculateTotal(Order order, string customerId)
    {
        var discount = _prices.GetDiscount(customerId);
        return order.Items.Sum(i => i.Price * i.Quantity) * (1 - discount);
    }
}

public record OrderItem(string Sku, decimal Price, int Quantity);
public record Order(List<OrderItem> Items);

// ── xUnit tests ────────────────────────────────────────────────────────
public class OrderCalculatorTests
{
    [Fact]
    public void CalculateTotal_WithDiscount_ReturnsDiscountedSum()
    {
        // Arrange
        var mockPrice = new Mock<IPriceService>();
        mockPrice.Setup(p => p.GetDiscount("vip")).Returns(0.20m);

        var calculator = new OrderCalculator(mockPrice.Object);
        var order = new Order(new List<OrderItem>
        {
            new("ABC", 100m, 2),
            new("DEF", 50m,  1)
        });

        // Act
        var total = calculator.CalculateTotal(order, "vip");

        // Assert (FluentAssertions)
        total.Should().Be(200m);    // (200 + 50) * 0.80
    }

    [Theory]
    [InlineData("standard", 0.00, 250.00)]
    [InlineData("vip",      0.20, 200.00)]
    [InlineData("employee", 0.35, 162.50)]
    public void CalculateTotal_MultipleDiscountLevels_ReturnsExpected(
        string customerId, decimal discount, decimal expected)
    {
        var mockPrice = new Mock<IPriceService>();
        mockPrice.Setup(p => p.GetDiscount(customerId)).Returns(discount);

        var calculator = new OrderCalculator(mockPrice.Object);
        var order = new Order(new List<OrderItem> { new("SKU", 100m, 2), new("SKU2", 50m, 1) });

        var total = calculator.CalculateTotal(order, customerId);
        total.Should().BeApproximately(expected, 0.001m);
    }

    [Fact]
    public void CalculateTotal_NoItems_ReturnsZero()
    {
        var mockPrice = new Mock<IPriceService>();
        var calculator = new OrderCalculator(mockPrice.Object);
        var empty = new Order(new List<OrderItem>());

        var total = calculator.CalculateTotal(empty, "test");

        total.Should().Be(0m);
    }
}

/* ── NUnit equivalent (for reference) ──────────────────────────────────
[TestFixture]
public class OrderCalculatorNUnitTests
{
    private Mock<IPriceService> _mockPrice = null!;
    private OrderCalculator _calculator = null!;

    [SetUp]
    public void Setup()
    {
        _mockPrice = new Mock<IPriceService>();
        _calculator = new OrderCalculator(_mockPrice.Object);
    }

    [Test]
    public void CalculateTotal_WithDiscount_ReturnsDiscountedSum()
    {
        _mockPrice.Setup(p => p.GetDiscount("vip")).Returns(0.20m);
        var order = new Order(new List<OrderItem> { new("ABC", 100m, 2) });

        var total = _calculator.CalculateTotal(order, "vip");

        Assert.That(total, Is.EqualTo(160m).Within(0.001));
    }
}
*/

```
