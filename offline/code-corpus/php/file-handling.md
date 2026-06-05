---
language: php
tags: [io, pattern]
title: File Handling
description: File read/write, CSV parsing, directory iteration via fopen/fgets/fwrite and file_* functions.
source: pattern
---

```php
<?php

// --- Basic file reading ---
$content = file_get_contents('/path/to/file.txt');

// Line-by-line (memory efficient)
$handle = fopen('/path/to/large-file.txt', 'r');
if ($handle) {
    while (($line = fgets($handle)) !== false) {
        echo $line;
    }
    fclose($handle);
}

// --- Writing ---
file_put_contents('/path/to/output.txt', 'Hello, World!');

$handle = fopen('/path/to/output.txt', 'w');
fwrite($handle, "Line 1\n");
fwrite($handle, "Line 2\n");
fclose($handle);

// Append mode
file_put_contents('/path/to/log.txt', "New entry\n", FILE_APPEND | LOCK_EX);

// --- CSV handling ---
$handle = fopen('/path/to/data.csv', 'r');
$headers = fgetcsv($handle); // read header row
$rows = [];
while (($row = fgetcsv($handle)) !== false) {
    $rows[] = array_combine($headers, $row);
}
fclose($handle);

// Write CSV
$handle = fopen('/path/to/output.csv', 'w');
fputcsv($handle, ['Name', 'Email', 'Age']);
fputcsv($handle, ['Alice', 'alice@example.com', 30]);
fputcsv($handle, ['Bob', 'bob@example.com', 25]);
fclose($handle);

// --- Directory iteration ---
$dir = '/path/to/dir';
if (is_dir($dir)) {
    $iterator = new DirectoryIterator($dir);
    foreach ($iterator as $fileinfo) {
        if (!$fileinfo->isDot()) {
            echo $fileinfo->getFilename() . ' - '
                 . ($fileinfo->isDir() ? 'dir' : 'file') . "\n";
        }
    }
}

// Recursive directory iterator
$rit = new RecursiveIteratorIterator(
    new RecursiveDirectoryIterator($dir, RecursiveDirectoryIterator::SKIP_DOTS)
);
foreach ($rit as $file) {
    if ($file->isFile() && $file->getExtension() === 'php') {
        echo $file->getPathname() . "\n";
    }
}

```
