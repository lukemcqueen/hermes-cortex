---
language: dart
tags: [flutter, widgets, dart, mobile]
title: Flutter Widget Composition
description: StatelessWidget, StatefulWidget, InheritedWidget, BuildContext, composition vs inheritance
source: pattern
---

## StatelessWidget

```dart
import 'package:flutter/material.dart';

class UserAvatar extends StatelessWidget {
  const UserAvatar({
    super.key,
    required this.name,
    this.avatarUrl,
    this.size = 48,
    this.onTap,
  });

  final String name;
  final String? avatarUrl;
  final double size;
  final VoidCallback? onTap;

  String get _initials {
    final parts = name.split(' ');
    if (parts.length >= 2) {
      return '${parts.first[0]}${parts.last[0]}'.toUpperCase();
    }
    return name.isNotEmpty ? name[0].toUpperCase() : '?';
  }

  Color _colorFromName(String name) {
    final hash = name.hashCode;
    return Colors.primaries[hash.abs() % Colors.primaries.length];
  }

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: CircleAvatar(
        radius: size / 2,
        backgroundColor: _colorFromName(name).withOpacity(0.2),
        backgroundImage: avatarUrl != null ? NetworkImage(avatarUrl!) : null,
        child: avatarUrl == null
            ? Text(
                _initials,
                style: TextStyle(
                  color: _colorFromName(name),
                  fontWeight: FontWeight.w600,
                  fontSize: size * 0.4,
                ),
              )
            : null,
      ),
    );
  }
}
```

## StatefulWidget

```dart
import 'package:flutter/material.dart';

class AccordionCard extends StatefulWidget {
  const AccordionCard({
    super.key,
    required this.title,
    required this.child,
    this.initiallyExpanded = false,
    this.onExpansionChanged,
  });

  final String title;
  final Widget child;
  final bool initiallyExpanded;
  final ValueChanged<bool>? onExpansionChanged;

  @override
  State<AccordionCard> createState() => _AccordionCardState();
}

class _AccordionCardState extends State<AccordionCard>
    with SingleTickerProviderStateMixin {
  late bool _isExpanded;
  late AnimationController _animationController;
  late Animation<double> _expandAnimation;

  @override
  void initState() {
    super.initState();
    _isExpanded = widget.initiallyExpanded;
    _animationController = AnimationController(
      duration: const Duration(milliseconds: 200),
      vsync: this,
    );
    _expandAnimation = CurvedAnimation(
      parent: _animationController,
      curve: Curves.easeInOut,
    );
    if (_isExpanded) _animationController.value = 1.0;
  }

  @override
  void dispose() {
    _animationController.dispose();
    super.dispose();
  }

  void _toggle() {
    setState(() {
      _isExpanded = !_isExpanded;
      if (_isExpanded) {
        _animationController.forward();
      } else {
        _animationController.reverse();
      }
      widget.onExpansionChanged?.call(_isExpanded);
    });
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Card(
      margin: const EdgeInsets.symmetric(vertical: 4),
      child: Column(
        children: [
          InkWell(
            onTap: _toggle,
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Row(
                children: [
                  Expanded(
                    child: Text(
                      widget.title,
                      style: theme.textTheme.titleMedium,
                    ),
                  ),
                  RotationTransition(
                    turns: _expandAnimation,
                    child: const Icon(Icons.expand_more),
                  ),
                ],
              ),
            ),
          ),
          SizeTransition(
            sizeFactor: _expandAnimation,
            axisAlignment: -1.0,
            child: Padding(
              padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
              child: widget.child,
            ),
          ),
        ],
      ),
    );
  }
}
```

## InheritedWidget (Context-based DI)

```dart
import 'package:flutter/material.dart';

/* ---------- Theme provider using InheritedWidget ---------- */
class AppTheme extends InheritedWidget {
  const AppTheme({
    super.key,
    required this.colors,
    required this.typography,
    required super.child,
  });

  final AppColors colors;
  final AppTypography typography;

  static AppTheme of(BuildContext context) {
    final widget = context.dependOnInheritedWidgetOfExactType<AppTheme>();
    assert(widget != null, 'No AppTheme found in context');
    return widget!;
  }

  @override
  bool updateShouldNotify(AppTheme oldWidget) {
    return colors != oldWidget.colors || typography != oldWidget.typography;
  }
}

class AppColors {
  const AppColors({
    required this.primary,
    required this.secondary,
    required this.background,
    required this.surface,
    required this.text,
    required this.textSecondary,
    required this.error,
  });

  final Color primary;
  final Color secondary;
  final Color background;
  final Color surface;
  final Color text;
  final Color textSecondary;
  final Color error;

  static const light = AppColors(
    primary: Color(0xFF3B82F6),
    secondary: Color(0xFF8B5CF6),
    background: Color(0xFFF9FAFB),
    surface: Color(0xFFFFFFFF),
    text: Color(0xFF111827),
    textSecondary: Color(0xFF6B7280),
    error: Color(0xFFEF4444),
  );

  static const dark = AppColors(
    primary: Color(0xFF60A5FA),
    secondary: Color(0xFFA78BFA),
    background: Color(0xFF111827),
    surface: Color(0xFF1F2937),
    text: Color(0xFFF3F4F6),
    textSecondary: Color(0xFF9CA3AF),
    error: Color(0xFFFCA5A5),
  );
}

class AppTypography {
  const AppTypography({
    required this.displayLarge,
    required this.headline,
    required this.title,
    required this.body,
    required this.caption,
  });

  final TextStyle displayLarge;
  final TextStyle headline;
  final TextStyle title;
  final TextStyle body;
  final TextStyle caption;

  static const base = AppTypography(
    displayLarge: TextStyle(fontSize: 32, fontWeight: FontWeight.bold, letterSpacing: -0.5),
    headline: TextStyle(fontSize: 24, fontWeight: FontWeight.semibold),
    title: TextStyle(fontSize: 18, fontWeight: FontWeight.w600),
    body: TextStyle(fontSize: 14, fontWeight: FontWeight.normal, height: 1.5),
    caption: TextStyle(fontSize: 12, fontWeight: FontWeight.normal, color: Color(0xFF6B7280)),
  );
}

/* ---------- Builder widget using inherited theme ---------- */
class ThemedText extends StatelessWidget {
  const ThemedText(this.text, {super.key, this.variant = 'body', this.color});

  final String text;
  final String variant;
  final Color? color;

  @override
  Widget build(BuildContext context) {
    final typography = AppTheme.of(context).typography;
    final colors = AppTheme.of(context).colors;

    TextStyle style;
    switch (variant) {
      case 'display':
        style = typography.displayLarge;
        break;
      case 'headline':
        style = typography.headline;
        break;
      case 'title':
        style = typography.title;
        break;
      case 'caption':
        style = typography.caption;
        break;
      default:
        style = typography.body;
    }

    return Text(
      text,
      style: style.copyWith(color: color ?? colors.text),
    );
  }
}

// Usage
void main() {
  runApp(
    const AppTheme(
      colors: AppColors.light,
      typography: AppTypography.base,
      child: MaterialApp(home: MyScreen()),
    ),
  );
}
```

## Composition vs Inheritance

```dart
import 'package:flutter/material.dart';

/*
 * FLUTTER FAVORS COMPOSITION OVER INHERITANCE
 *
 * Instead of extending a base widget class and overriding methods,
 * Flutter composes small focused widgets.
 */

/* ---------- ❌ Inheritance approach (anti-pattern) ---------- */
class BaseButton extends StatelessWidget {
  const BaseButton({super.key, required this.label, this.onPressed});
  final String label;
  final VoidCallback? onPressed;

  @override
  Widget build(BuildContext context) {
    return ElevatedButton(
      onPressed: onPressed,
      child: Text(label),
    );
  }
}

// Problems: rigid, hard to customize, deep hierarchy
class IconButton extends BaseButton {
  const IconButton({
    super.key,
    required super.label,
    super.onPressed,
    required this.icon,
  });
  final IconData icon;

  @override
  Widget build(BuildContext context) {
    return ElevatedButton.icon(
      onPressed: onPressed,
      icon: Icon(icon),
      label: Text(label),
    );
  }
}

/* ---------- ✅ Composition approach ---------- */
// Small, focused, reusable widgets that can be combined freely

class ButtonBuilder extends StatelessWidget {
  const ButtonBuilder({
    super.key,
    required this.child,
    this.onPressed,
    this.variant = _ButtonVariant.primary,
    this.fullWidth = false,
    this.size = _ButtonSize.md,
  });

  final Widget child;
  final VoidCallback? onPressed;
  final _ButtonVariant variant;
  final bool fullWidth;
  final _ButtonSize size;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    Color bgColor;
    Color textColor;

    switch (variant) {
      case _ButtonVariant.primary:
        bgColor = theme.colorScheme.primary;
        textColor = theme.colorScheme.onPrimary;
      case _ButtonVariant.secondary:
        bgColor = theme.colorScheme.secondaryContainer;
        textColor = theme.colorScheme.onSecondaryContainer;
      case _ButtonVariant.outline:
        bgColor = Colors.transparent;
        textColor = theme.colorScheme.primary;
    }

    final EdgeInsets padding;
    switch (size) {
      case _ButtonSize.sm:
        padding = const EdgeInsets.symmetric(horizontal: 12, vertical: 6);
      case _ButtonSize.md:
        padding = const EdgeInsets.symmetric(horizontal: 20, vertical: 12);
      case _ButtonSize.lg:
        padding = const EdgeInsets.symmetric(horizontal: 28, vertical: 16);
    }

    return SizedBox(
      width: fullWidth ? double.infinity : null,
      child: TextButton(
        onPressed: onPressed,
        style: TextButton.styleFrom(
          backgroundColor: bgColor,
          foregroundColor: textColor,
          padding: padding,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(8),
            side: variant == _ButtonVariant.outline
                ? BorderSide(color: theme.colorScheme.primary)
                : BorderSide.none,
          ),
        ),
        child: child,
      ),
    );
  }
}

enum _ButtonVariant { primary, secondary, outline }
enum _ButtonSize { sm, md, lg }

/* Compose specific buttons from the generic builder */
class PrimaryButton extends StatelessWidget {
  const PrimaryButton({super.key, required this.label, this.onPressed, this.fullWidth = false});
  final String label;
  final VoidCallback? onPressed;
  final bool fullWidth;

  @override
  Widget build(BuildContext context) {
    return ButtonBuilder(
      onPressed: onPressed,
      fullWidth: fullWidth,
      child: Text(label),
    );
  }
}

class IconLabelButton extends StatelessWidget {
  const IconLabelButton({
    super.key,
    required this.label,
    required this.icon,
    this.onPressed,
    this.variant = _ButtonVariant.primary,
  });
  final String label;
  final IconData icon;
  final VoidCallback? onPressed;
  final _ButtonVariant variant;

  @override
  Widget build(BuildContext context) {
    return ButtonBuilder(
      onPressed: onPressed,
      variant: variant,
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 18),
          const SizedBox(width: 8),
          Text(label),
        ],
      ),
    );
  }
}

/* ---------- Composition with BuildContext ---------- */
class ResponsiveLayout extends StatelessWidget {
  const ResponsiveLayout({
    super.key,
    required this.mobile,
    required this.tablet,
    required this.desktop,
  });

  final Widget mobile;
  final Widget tablet;
  final Widget desktop;

  static bool isMobile(BuildContext context) =>
      MediaQuery.of(context).size.width < 640;

  static bool isTablet(BuildContext context) =>
      MediaQuery.of(context).size.width >= 640 &&
      MediaQuery.of(context).size.width < 1024;

  static bool isDesktop(BuildContext context) =>
      MediaQuery.of(context).size.width >= 1024;

  @override
  Widget build(BuildContext context) {
    final width = MediaQuery.of(context).size.width;
    if (width >= 1024) return desktop;
    if (width >= 640) return tablet;
    return mobile;
  }
}

// Usage
class MyScreen extends StatelessWidget {
  const MyScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Composition Example')),
      body: ResponsiveLayout(
        mobile: const Column(
          children: [
            IconLabelButton(label: 'Add Item', icon: Icons.add),
            SizedBox(height: 8),
            PrimaryButton(label: 'Submit', fullWidth: true),
          ],
        ),
        tablet: const Row(
          children: [
            IconLabelButton(label: 'Add', icon: Icons.add),
            SizedBox(width: 12),
            PrimaryButton(label: 'Submit'),
          ],
        ),
        desktop: const Row(
          mainAxisAlignment: MainAxisAlignment.end,
          children: [
            IconLabelButton(
              label: 'Add New Item',
              icon: Icons.add,
              variant: _ButtonVariant.secondary,
            ),
            SizedBox(width: 12),
            PrimaryButton(label: 'Submit Changes'),
          ],
        ),
      ),
    );
  }
}
```