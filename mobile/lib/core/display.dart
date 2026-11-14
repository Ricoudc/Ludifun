import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// Taille du texte choisie sur ce téléphone (§5.94), en plus de celle du système.
enum TextSize {
  normal(1.0, 'Normal'),
  large(1.2, 'Grand'),
  larger(1.4, 'Très grand');

  const TextSize(this.factor, this.label);

  final double factor;
  final String label;
}

/// Affichage choisi sur ce téléphone (§5.94) : taille du texte, lecture facile (lettres et mots
/// plus espacés, lignes plus hautes : ce qui aide un lecteur dyslexique), contraste renforcé.
class DisplaySettings {
  const DisplaySettings({
    this.textSize = TextSize.normal,
    this.easyReading = false,
    this.highContrast = false,
  });

  factory DisplaySettings.fromJson(Map<String, Object?> json) => DisplaySettings(
    textSize: TextSize.values.firstWhere(
      (s) => s.name == json['text_size'],
      orElse: () => TextSize.normal,
    ),
    easyReading: json['easy_reading'] == true,
    highContrast: json['high_contrast'] == true,
  );

  final TextSize textSize;
  final bool easyReading;
  final bool highContrast;

  Map<String, Object?> toJson() => {
    'text_size': textSize.name,
    'easy_reading': easyReading,
    'high_contrast': highContrast,
  };

  DisplaySettings copyWith({TextSize? textSize, bool? easyReading, bool? highContrast}) =>
      DisplaySettings(
        textSize: textSize ?? this.textSize,
        easyReading: easyReading ?? this.easyReading,
        highContrast: highContrast ?? this.highContrast,
      );
}

abstract interface class DisplaySettingStore {
  Future<DisplaySettings?> read();

  Future<void> write(DisplaySettings settings);
}

class SecureDisplaySettingStore implements DisplaySettingStore {
  const SecureDisplaySettingStore([this._storage = const FlutterSecureStorage()]);

  static const key = 'ludifun.display';
  final FlutterSecureStorage _storage;

  @override
  Future<DisplaySettings?> read() async {
    try {
      final raw = await _storage.read(key: key);
      if (raw == null) return null;
      return DisplaySettings.fromJson((jsonDecode(raw) as Map).cast<String, Object?>());
    } on Object {
      return null; // illisible : affichage normal
    }
  }

  @override
  Future<void> write(DisplaySettings settings) async {
    try {
      await _storage.write(key: key, value: jsonEncode(settings.toJson()));
    } on Object {
      // réglage non gardé : il vaut jusqu'à la fermeture de l'application
    }
  }
}

class MemoryDisplaySettingStore implements DisplaySettingStore {
  MemoryDisplaySettingStore([this.value]);

  DisplaySettings? value;

  @override
  Future<DisplaySettings?> read() async => value;

  @override
  Future<void> write(DisplaySettings settings) async => value = settings;
}

final displaySettingStoreProvider = Provider<DisplaySettingStore>(
  (ref) => const SecureDisplaySettingStore(),
);

final displayProvider = AsyncNotifierProvider<DisplayController, DisplaySettings>(
  DisplayController.new,
);

class DisplayController extends AsyncNotifier<DisplaySettings> {
  @override
  Future<DisplaySettings> build() async =>
      await ref.read(displaySettingStoreProvider).read() ?? const DisplaySettings();

  Future<void> change(DisplaySettings settings) async {
    state = AsyncData(settings);
    await ref.read(displaySettingStoreProvider).write(settings);
  }
}

TextStyle? _easy(TextStyle? style) =>
    style?.copyWith(letterSpacing: 0.8, wordSpacing: 3, height: 1.5, fontStyle: FontStyle.normal);

/// Le thème de Ludifun, avec l'affichage choisi.
ThemeData applyDisplay(ThemeData theme, DisplaySettings settings) {
  var result = theme;
  if (settings.easyReading) {
    final t = result.textTheme;
    result = result.copyWith(
      textTheme: t.copyWith(
        displayLarge: _easy(t.displayLarge),
        displayMedium: _easy(t.displayMedium),
        displaySmall: _easy(t.displaySmall),
        headlineLarge: _easy(t.headlineLarge),
        headlineMedium: _easy(t.headlineMedium),
        headlineSmall: _easy(t.headlineSmall),
        titleLarge: _easy(t.titleLarge),
        titleMedium: _easy(t.titleMedium),
        titleSmall: _easy(t.titleSmall),
        bodyLarge: _easy(t.bodyLarge),
        bodyMedium: _easy(t.bodyMedium),
        bodySmall: _easy(t.bodySmall),
        labelLarge: _easy(t.labelLarge),
        labelMedium: _easy(t.labelMedium),
        labelSmall: _easy(t.labelSmall),
      ),
    );
  }
  if (settings.highContrast) {
    result = result.copyWith(
      scaffoldBackgroundColor: Colors.white,
      colorScheme: result.colorScheme.copyWith(
        surface: Colors.white,
        onSurface: Colors.black,
        onSurfaceVariant: Colors.black87,
        outline: Colors.black54,
      ),
      textTheme: result.textTheme.apply(bodyColor: Colors.black, displayColor: Colors.black),
    );
  }
  return result;
}

/// Applique la taille du texte choisie, en plus de celle du système.
Widget withTextSize(BuildContext context, DisplaySettings settings, Widget child) {
  if (settings.textSize == TextSize.normal) return child;
  final media = MediaQuery.of(context);
  return MediaQuery(
    data: media.copyWith(
      textScaler: TextScaler.linear(media.textScaler.scale(1) * settings.textSize.factor),
    ),
    child: child,
  );
}

/// « Affichage » : le réglage, en bas de l'écran, pour l'enfant comme pour le parent.
Future<void> showDisplaySheet(BuildContext context) => showModalBottomSheet<void>(
  context: context,
  showDragHandle: true,
  isScrollControlled: true,
  builder: (_) => const _DisplaySheet(),
);

class _DisplaySheet extends ConsumerWidget {
  const _DisplaySheet();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final settings = ref.watch(displayProvider).value ?? const DisplaySettings();
    void change(DisplaySettings next) => ref.read(displayProvider.notifier).change(next);
    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(20, 0, 20, 16),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text('Affichage', style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: 4),
            const Text('Gardé sur ce téléphone.', style: TextStyle(color: Colors.black54)),
            const SizedBox(height: 12),
            const Text('Taille du texte', style: TextStyle(fontWeight: FontWeight.w700)),
            const SizedBox(height: 8),
            SegmentedButton<TextSize>(
              segments: [
                for (final size in TextSize.values)
                  ButtonSegment(value: size, label: Text(size.label)),
              ],
              selected: {settings.textSize},
              onSelectionChanged: (choice) => change(settings.copyWith(textSize: choice.first)),
            ),
            const SizedBox(height: 8),
            SwitchListTile(
              contentPadding: EdgeInsets.zero,
              value: settings.easyReading,
              onChanged: (on) => change(settings.copyWith(easyReading: on)),
              title: const Text('Lecture facile'),
              subtitle: const Text('Lettres et mots plus espacés, lignes plus hautes.'),
            ),
            SwitchListTile(
              contentPadding: EdgeInsets.zero,
              value: settings.highContrast,
              onChanged: (on) => change(settings.copyWith(highContrast: on)),
              title: const Text('Contraste renforcé'),
              subtitle: const Text('Texte noir sur fond blanc.'),
            ),
          ],
        ),
      ),
    );
  }
}
