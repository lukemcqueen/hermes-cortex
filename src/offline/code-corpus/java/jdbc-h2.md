---
language: java
tags: [pattern, database]
title: JDBC & H2 Database
description: DriverManager, Connection, PreparedStatement, ResultSet, executeQuery/executeUpdate with H2 in-memory DB.
source: pattern
---

```java
import java.sql.*;

public class JdbcDemo {
    public static void main(String[] args) throws Exception {
        // H2 in-memory database (add h2-2.2.x.jar to classpath)
        String url = "jdbc:h2:mem:testdb";
        String user = "sa";
        String pass = "";

        try (Connection conn = DriverManager.getConnection(url, user, pass);
             Statement stmt = conn.createStatement()) {

            // Create table
            stmt.executeUpdate("""
                    CREATE TABLE users (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        name VARCHAR(100) NOT NULL,
                        email VARCHAR(100)
                    )
                    """);

            // Insert with PreparedStatement
            try (PreparedStatement ps = conn.prepareStatement(
                    "INSERT INTO users (name, email) VALUES (?, ?)")) {
                ps.setString(1, "Alice");
                ps.setString(2, "alice@example.com");
                ps.executeUpdate();

                ps.setString(1, "Bob");
                ps.setString(2, "bob@example.com");
                ps.executeUpdate();
            }

            // Query
            try (PreparedStatement ps = conn.prepareStatement(
                    "SELECT * FROM users WHERE name = ?")) {
                ps.setString(1, "Alice");
                try (ResultSet rs = ps.executeQuery()) {
                    while (rs.next()) {
                        int id = rs.getInt("id");
                        String name = rs.getString("name");
                        String email = rs.getString("email");
                        System.out.printf("User: id=%d, name=%s, email=%s%n",
                                          id, name, email);
                    }
                }
            }

            // Count
            try (ResultSet rs = stmt.executeQuery("SELECT COUNT(*) FROM users")) {
                if (rs.next()) {
                    System.out.println("Total users: " + rs.getInt(1));
                }
            }
        }
    }
}

```
