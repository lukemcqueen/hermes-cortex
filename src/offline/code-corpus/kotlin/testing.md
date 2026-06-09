---
language: kotlin
tags: [kotlin, test, JUnit, kotlin.test, shouldBe, AssertJ, MockK, BeforeEach]
title: Testing
description: Covers Kotlin testing with kotlin.test, JUnit 5, AssertJ assertions, MockK for mocking, and common test patterns.
source: pattern
---

```kotlin
import kotlin.test.*
import org.junit.jupiter.api.*
import org.junit.jupiter.api.Assertions.*
import io.mockk.*
import org.assertj.core.api.Assertions.assertThat

// kotlin.test style
class SimpleTest {
    @Test
    fun `addition works`() {
        assertEquals(4, 2 + 2)
    }

    @Test
    fun `string contains`() {
        assertTrue("hello".contains("el"))
        assertFalse("hello".contains("x"))
    }
}

// JUnit 5 with AssertJ
class AssertJTest {
    @Test
    fun `assertj fluent assertions`() {
        val list = listOf(1, 2, 3)
        assertThat(list)
            .hasSize(3)
            .contains(2)
            .allMatch { it > 0 }
    }
}

// MockK
class UserService(private val repo: UserRepository) {
    fun getUser(id: Int): String = repo.findById(id) ?: "default"
}

interface UserRepository {
    fun findById(id: Int): String?
}

class MockKTest {
    @Test
    fun `mock example`() {
        val repo = mockk<UserRepository>()
        every { repo.findById(1) } returns "Alice"
        every { repo.findById(any()) } returns null

        val service = UserService(repo)
        assertEquals("Alice", service.getUser(1))
        assertEquals("default", service.getUser(99))
    }
}

// @BeforeEach / @AfterEach
class LifecycleTest {
    private var counter = 0

    @BeforeEach
    fun setup() {
        counter = 0
    }

    @Test
    fun `first test`() { counter++; assertEquals(1, counter) }

    @Test
    fun `second test`() { counter++; assertEquals(1, counter) }
}

```
