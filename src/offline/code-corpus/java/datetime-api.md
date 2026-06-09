---
language: java
tags: [pattern, util]
title: Date-Time API (java.time)
description: LocalDate, LocalDateTime, ZonedDateTime, DateTimeFormatter, Duration, and Period.
source: pattern
---

```java
import java.time.*;
import java.time.format.*;
import java.time.temporal.*;

public class DateTimeDemo {
    public static void main(String[] args) {
        // LocalDate
        LocalDate today = LocalDate.now();
        LocalDate independenceDay = LocalDate.of(1776, Month.JULY, 4);
        Period between = Period.between(independenceDay, today);
        System.out.printf("%d years, %d months, %d days%n",
                          between.getYears(), between.getMonths(), between.getDays());

        // LocalDateTime
        LocalDateTime now = LocalDateTime.now();
        LocalDateTime meeting = LocalDateTime.of(2025, 6, 10, 14, 30);
        Duration duration = Duration.between(now, meeting);
        System.out.println("Hours until meeting: " + duration.toHours());

        // ZonedDateTime
        ZonedDateTime nyc = ZonedDateTime.now(ZoneId.of("America/New_York"));
        ZonedDateTime paris = nyc.withZoneSameInstant(ZoneId.of("Europe/Paris"));
        System.out.println("NYC: " + nyc + " -> Paris: " + paris);

        // Formatting
        DateTimeFormatter fmt = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss");
        System.out.println("Formatted: " + now.format(fmt));

        DateTimeFormatter isoFmt = DateTimeFormatter.ISO_LOCAL_DATE_TIME;
        LocalDateTime parsed = LocalDateTime.parse("2025-06-10T14:30:00", isoFmt);
        System.out.println("Parsed: " + parsed);

        // Arithmetic
        LocalDate nextWeek = today.plusWeeks(1);
        LocalDate lastMonth = today.minus(1, ChronoUnit.MONTHS);
        System.out.println("Next week: " + nextWeek + ", Last month: " + lastMonth);

        // Instant (machine time)
        Instant epoch = Instant.EPOCH;
        Instant nowInstant = Instant.now();
        System.out.println("Seconds since epoch: " + Duration.between(epoch, nowInstant).getSeconds());
    }
}

```
