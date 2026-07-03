---
language: php
tags: [date, pattern]
title: DateTime & Carbon
description: DateTime and DateTimeImmutable classes, Carbon library usage: diff, format, timezone handling.
source: pattern
---

```php
<?php

// --- Built-in DateTime ---
$now = new DateTime();
echo $now->format('Y-m-d H:i:s');          // 2026-06-05 12:00:00

$immutable = new DateTimeImmutable();
$future = $immutable->modify('+7 days');    // Returns new object (immutable)
echo $future->format('Y-m-d');

// Timezone handling
$tz = new DateTimeZone('America/New_York');
$dt = new DateTime('now', $tz);
echo $dt->format('Y-m-d H:i:s T');

// Convert timezone
$dt->setTimezone(new DateTimeZone('UTC'));
echo $dt->format('Y-m-d H:i:s');

// Date intervals
$start = new DateTime('2026-01-01');
$end   = new DateTime('2026-12-31');
$diff  = $start->diff($end);
echo $diff->days;      // 364
echo $diff->format('%y years %m months');

// DatePeriod iteration
$period = new DatePeriod(
    new DateTime('2026-01-01'),
    new DateInterval('P1M'),
    new DateTime('2026-12-31'),
);
foreach ($period as $date) {
    echo $date->format('Y-m-d') . "\n";
}

// --- Carbon (if installed via Composer) ---
// use Carbon\Carbon;
// use Carbon\CarbonImmutable;
//
// Carbon::setLocale('fr');
// echo Carbon::now()->addDays(5)->diffForHumans();       // dans 5 jours
// echo Carbon::now()->subWeek()->diffForHumans();        // il y a 1 semaine
//
// $created = Carbon::parse('2026-01-15');
// echo $created->diffInDays();                           // days since
// echo $created->startOfMonth()->format('Y-m-d');        // 2026-01-01
// echo $created->endOfMonth()->format('Y-m-d');          // 2026-01-31

```
