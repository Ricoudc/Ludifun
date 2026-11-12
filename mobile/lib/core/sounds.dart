import 'package:audioplayers/audioplayers.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// Petits sons des séances (fichiers synthétisés par `tool/sons.py`).
enum Sound { correct, partial, wrong, star, finish }

abstract interface class SoundPlayer {
  Future<void> play(Sound sound);
}

/// Les sons du téléphone ; un téléphone muet ou sans lecteur ne fait simplement rien.
class AssetSoundPlayer implements SoundPlayer {
  AudioPlayer? _player;

  @override
  Future<void> play(Sound sound) async {
    try {
      final player = _player ??= AudioPlayer();
      await player.setReleaseMode(ReleaseMode.stop);
      await player.stop();
      await player.play(AssetSource('sounds/${sound.name}.wav'), mode: PlayerMode.lowLatency);
    } on Object {
      // pas de son : la séance continue
    }
  }
}

final soundPlayerProvider = Provider<SoundPlayer>((ref) => AssetSoundPlayer());

/// Sons activés ou non, gardé sur le téléphone (bouton 🔊 / 🔇 de la séance).
abstract interface class SoundSettingStore {
  Future<bool?> read();

  Future<void> write(bool on);
}

class SecureSoundSettingStore implements SoundSettingStore {
  const SecureSoundSettingStore([this._storage = const FlutterSecureStorage()]);

  static const key = 'ludifun.sound';
  final FlutterSecureStorage _storage;

  @override
  Future<bool?> read() async {
    try {
      return switch (await _storage.read(key: key)) {
        'on' => true,
        'off' => false,
        _ => null,
      };
    } on Object {
      return null;
    }
  }

  @override
  Future<void> write(bool on) async {
    try {
      await _storage.write(key: key, value: on ? 'on' : 'off');
    } on Object {
      // réglage non gardé : il vaut pour cette fois
    }
  }
}

class MemorySoundSettingStore implements SoundSettingStore {
  MemorySoundSettingStore([this.value]);

  bool? value;

  @override
  Future<bool?> read() async => value;

  @override
  Future<void> write(bool on) async => value = on;
}

final soundSettingStoreProvider = Provider<SoundSettingStore>(
  (ref) => const SecureSoundSettingStore(),
);

final soundOnProvider = AsyncNotifierProvider<SoundOnController, bool>(SoundOnController.new);

class SoundOnController extends AsyncNotifier<bool> {
  @override
  Future<bool> build() async => await ref.read(soundSettingStoreProvider).read() ?? true;

  Future<void> toggle() async {
    final on = !(state.value ?? true);
    state = AsyncData(on);
    await ref.read(soundSettingStoreProvider).write(on);
  }
}

/// Les sons de la séance, joués seulement s'ils sont activés.
class Sounds {
  Sounds(this._ref);

  final Ref _ref;

  void play(Sound sound) {
    if (_ref.read(soundOnProvider).value ?? true) _ref.read(soundPlayerProvider).play(sound);
  }
}

final soundsProvider = Provider<Sounds>(Sounds.new);
