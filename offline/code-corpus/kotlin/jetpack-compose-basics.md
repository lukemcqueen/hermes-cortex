---
language: kotlin
tags: [kotlin, Compose, Composable, Column, Row, Box, mutableStateOf, LazyColumn]
title: Jetpack Compose Basics
description: Covers fundamental Jetpack Compose patterns: @Composable functions, Column/Row/Box layout, mutableStateOf, LazyColumn, and recomposition.
source: pattern
---

```kotlin
import androidx.compose.runtime.*
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp

// Simple composable
@Composable
fun Greeting(name: String) {
    Text(text = "Hello, $name!")
}

// State & recomposition
@Composable
fun Counter() {
    var count by remember { mutableStateOf(0) }

    Column(modifier = Modifier.padding(16.dp)) {
        Text("Count: $count", style = MaterialTheme.typography.headlineMedium)

        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Button(onClick = { count-- }) { Text("-") }
            Button(onClick = { count++ }) { Text("+") }
        }
    }
}

// LazyColumn (RecyclerView equivalent)
data class Item(val id: Int, val title: String)

@Composable
fun ItemList(items: List<Item>) {
    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(horizontal = 16.dp, vertical = 8.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp)
    ) {
        items(items, key = { it.id }) { item ->
            Card(modifier = Modifier.fillMaxWidth()) {
                Text(
                    text = item.title,
                    modifier = Modifier.padding(16.dp)
                )
            }
        }
    }
}

```
