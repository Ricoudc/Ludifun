import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ludifun/features/capture/capture_controller.dart';

import '../support/fakes.dart';

void main() {
  test('seules les photos de la leçon analysée sont effacées (§15)', () async {
    final container = ProviderContainer(
      overrides: [imagePickerProvider.overrideWithValue(FakeImagePicker(gallery: 2))],
    );
    addTearDown(container.dispose);
    final capture = container.read(captureProvider.notifier);

    await capture.pickFromGallery();
    capture.markSent('l1');
    capture.analysisFinished('l2'); // une autre leçon, ouverte depuis l'accueil
    expect(container.read(captureProvider), hasLength(2));

    capture.analysisFinished('l1');
    expect(container.read(captureProvider), isEmpty);

    // De nouvelles photos, pas encore envoyées : la fin d'une ancienne analyse ne les touche pas.
    await capture.pickFromGallery();
    capture.analysisFinished('l1');
    expect(container.read(captureProvider), hasLength(2));
  });

  test('réordonner et retirer des pages', () async {
    final container = ProviderContainer(
      overrides: [imagePickerProvider.overrideWithValue(FakeImagePicker(gallery: 3))],
    );
    addTearDown(container.dispose);
    final capture = container.read(captureProvider.notifier);
    await capture.pickFromGallery();
    capture.move(2, 0);
    expect(container.read(captureProvider).map((p) => p.path), [
      'page103.png',
      'page101.png',
      'page102.png',
    ]);
    capture.remove(1);
    expect(container.read(captureProvider).map((p) => p.path), ['page103.png', 'page102.png']);
  });
}
