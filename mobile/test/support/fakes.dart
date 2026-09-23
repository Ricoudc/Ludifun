import 'dart:convert';
import 'dart:typed_data';

import 'package:image_picker/image_picker.dart';
import 'package:ludifun/features/capture/image_compressor.dart';

/// Image PNG valide de 1 × 1 pixel.
final tinyPng = base64Decode(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==',
);

/// Appareil photo et galerie simulés : chaque appel rend les photos préparées.
class FakeImagePicker extends ImagePicker {
  FakeImagePicker({this.gallery = 2});

  int gallery;
  int cameraShots = 0;
  int? lastLimit;

  static XFile photo(int n) => XFile.fromData(tinyPng, name: 'page$n.png', path: 'page$n.png');

  @override
  Future<XFile?> pickImage({
    required ImageSource source,
    double? maxWidth,
    double? maxHeight,
    int? imageQuality,
    CameraDevice preferredCameraDevice = CameraDevice.rear,
    bool requestFullMetadata = true,
  }) async => photo(++cameraShots);

  @override
  Future<List<XFile>> pickMultiImage({
    double? maxWidth,
    double? maxHeight,
    int? imageQuality,
    int? limit,
    bool requestFullMetadata = true,
  }) async {
    lastLimit = limit;
    return [for (var i = 1; i <= gallery; i++) photo(100 + i)];
  }
}

/// Compression simulée : marque les octets pour vérifier qu'elle a bien eu lieu.
class FakeCompressor implements ImageCompressor {
  @override
  Future<Uint8List> compress(Uint8List original) async =>
      Uint8List.fromList([...utf8.encode('jpeg:'), ...original.take(4)]);
}
