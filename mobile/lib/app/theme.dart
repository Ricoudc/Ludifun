import 'package:flutter/material.dart';

/// Palette Ludifun V2 : joyeuse, lumineuse et lisible sans surcharge visuelle.
abstract final class LudiColors {
  static const primary = Color(0xFF356FC8);
  static const accent = Color(0xFFFFC857);
  static const background = Color(0xFFF6F8FC);
  static const surface = Color(0xFFFFFFFF);
  static const ink = Color(0xFF20304A);
  static const muted = Color(0xFF68778E);
  static const teal = Color(0xFF35A995);
  static const coral = Color(0xFFE98567);
  static const mastered = Color(0xFF269B78);
  static const toReview = Color(0xFFE5A12C);
  static const notMastered = Color(0xFFD95757);
}

ThemeData buildTheme() {
  const scheme = ColorScheme(
    brightness: Brightness.light, primary: LudiColors.primary, onPrimary: Colors.white,
    secondary: LudiColors.teal, onSecondary: Colors.white, error: LudiColors.notMastered,
    onError: Colors.white, surface: LudiColors.surface, onSurface: LudiColors.ink,
    surfaceContainerHighest: Color(0xFFEAF0F8), onSurfaceVariant: LudiColors.muted,
    outline: Color(0xFFDCE4EF), outlineVariant: Color(0xFFE8EDF4),
    shadow: Color(0x1A20304A), scrim: Colors.black54, inverseSurface: LudiColors.ink,
    onInverseSurface: Colors.white, inversePrimary: Color(0xFFB8D2FF),
  );
  final base = ThemeData(colorScheme: scheme, useMaterial3: true);
  final cardShape = RoundedRectangleBorder(borderRadius: BorderRadius.circular(20));
  return base.copyWith(
    scaffoldBackgroundColor: LudiColors.background,
    colorScheme: scheme,
    textTheme: base.textTheme.apply(bodyColor: LudiColors.ink, displayColor: LudiColors.ink).copyWith(
      headlineMedium: base.textTheme.headlineMedium?.copyWith(color: LudiColors.ink,
        fontWeight: FontWeight.w800, letterSpacing: -0.6),
      titleLarge: base.textTheme.titleLarge?.copyWith(color: LudiColors.ink,
        fontWeight: FontWeight.w800, letterSpacing: -0.2),
      bodyLarge: base.textTheme.bodyLarge?.copyWith(fontSize: 17, height: 1.4),
      bodyMedium: base.textTheme.bodyMedium?.copyWith(height: 1.35),
    ),
    appBarTheme: const AppBarTheme(backgroundColor: LudiColors.background,
      foregroundColor: LudiColors.ink, surfaceTintColor: Colors.transparent, centerTitle: false,
      titleTextStyle: TextStyle(color: LudiColors.ink, fontSize: 21, fontWeight: FontWeight.w800)),
    filledButtonTheme: FilledButtonThemeData(style: FilledButton.styleFrom(
      minimumSize: const Size.fromHeight(54), backgroundColor: LudiColors.primary,
      foregroundColor: Colors.white, elevation: 0,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      textStyle: const TextStyle(fontSize: 17, fontWeight: FontWeight.w800))),
    outlinedButtonTheme: OutlinedButtonThemeData(style: OutlinedButton.styleFrom(
      minimumSize: const Size.fromHeight(54), foregroundColor: LudiColors.primary,
      side: const BorderSide(color: Color(0xFFD7E2F0)),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      textStyle: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700))),
    textButtonTheme: TextButtonThemeData(style: TextButton.styleFrom(
      minimumSize: const Size(48, 48), foregroundColor: LudiColors.primary,
      textStyle: const TextStyle(fontSize: 15, fontWeight: FontWeight.w700))),
    cardTheme: CardThemeData(elevation: 0, color: LudiColors.surface,
      surfaceTintColor: Colors.transparent, shape: cardShape, margin: EdgeInsets.zero),
    inputDecorationTheme: InputDecorationTheme(helperMaxLines: 4, errorMaxLines: 4,
      filled: true, fillColor: Colors.white,
      contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 16),
      border: OutlineInputBorder(borderRadius: BorderRadius.circular(16),
        borderSide: const BorderSide(color: Color(0xFFDCE4EF))),
      enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(16),
        borderSide: const BorderSide(color: Color(0xFFDCE4EF))),
      focusedBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(16),
        borderSide: const BorderSide(color: LudiColors.primary, width: 1.6))),
    snackBarTheme: SnackBarThemeData(behavior: SnackBarBehavior.floating,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14))),
    chipTheme: base.chipTheme.copyWith(shape: RoundedRectangleBorder(
      borderRadius: BorderRadius.circular(12)), side: const BorderSide(color: Color(0xFFE4EAF2))),
  );
}
