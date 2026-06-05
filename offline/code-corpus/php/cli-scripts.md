---
language: php
tags: [cli, pattern]
title: CLI Scripts
description: PHP CLI: argv/getopt, php://input, Symfony Console commands, progress bars.
source: pattern
---

```php
<?php

// --- Basic CLI: argv and exit codes ---
// Run: php script.php --name=Alice --verbose
if (PHP_SAPI !== 'cli') {
    exit(1);
}

$options = getopt('', ['name::', 'verbose']);
$name    = $options['name'] ?? 'World';
$verbose = isset($options['verbose']);

echo "Hello, {$name}!\n";
if ($verbose) {
    echo "Verbose mode enabled\n";
    echo "Args: " . json_encode($argv) . "\n";
}

// --- Reading from stdin ---
$stdin = file_get_contents('php://stdin');
// echo strtoupper($stdin);

// --- Progress bar (pure PHP) ---
function progressBar(int $done, int $total, int $width = 50): void {
    $percent = ($total > 0) ? round($done / $total * 100) : 0;
    $fill    = round($width * $done / $total);
    $bar     = str_repeat('=', $fill) . str_repeat(' ', $width - $fill);
    echo "\r[" . $bar . "] {$percent}% ({$done}/{$total})";
    if ($done === $total) {
        echo "\n";
    }
}

$total = 50;
for ($i = 1; $i <= $total; $i++) {
    usleep(50000); // simulate work
    progressBar($i, $total);
}

// --- Symfony Console (requires symfony/console) ---
// use Symfony\Component\Console\Command\Command;
// use Symfony\Component\Console\Input\InputInterface;
// use Symfony\Component\Console\Output\OutputInterface;
// use Symfony\Component\Console\Input\InputOption;
// use Symfony\Component\Console\Application;
//
// class GreetCommand extends Command
// {
//     protected function configure(): void
//     {
//         $this->setName('app:greet')
//              ->addOption('name', null, InputOption::VALUE_REQUIRED, 'Who to greet')
//              ->addOption('yell', null, InputOption::VALUE_NONE, 'Yell the greeting');
//     }
//
//     protected function execute(InputInterface $input, OutputInterface $output): int
//     {
//         $name = $input->getOption('name') ?? 'World';
//         $text = "Hello, {$name}!";
//         if ($input->getOption('yell')) {
//             $text = strtoupper($text);
//         }
//         $output->writeln($text);
//         return Command::SUCCESS;
//     }
// }
//
// $app = new Application();
// $app->add(new GreetCommand());
// $app->run();

```
