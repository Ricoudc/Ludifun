import 'dart:math' as math;
import 'dart:ui' as ui;

import 'package:flutter/foundation.dart';
import 'package:flutter_image_compress/flutter_image_compress.dart';

/// §15 : côté long ≤ 2000 px, JPEG qualité 80, métadonnées EXIF supprimées (dont la
/// position GPS), avant tout envoi.
abstract interface class ImageCompressor {
  Future<Uint8List> compress(Uint8List original);
}

const maxLongSide = 2000;
const jpegQuality = 80;

/// Dimensions cibles : réduction proportionnelle, jamais d'agrandissement.
(int, int) targetSize(int width, int height) {
  final scale = math.min(1.0, maxLongSide / math.max(width, height));
  return ((width * scale).round(), (height * scale).round());
}

class NativeImageCompressor implements ImageCompressor {
  const NativeImageCompressor();

  @override
  Future<Uint8List> compress(Uint8List original) async {
    final buffer = await ui.ImmutableBuffer.fromUint8List(original);
    final descriptor = await ui.ImageDescriptor.encoded(buffer); // lit l'en-tête seulement
    final (width, height) = targetSize(descriptor.width, descriptor.height);
    descriptor.dispose();
    buffer.dispose();
    return FlutterImageCompress.compressWithList(
      original,
      minWidth: width,
      minHeight: height,
      quality: jpegQuality,
      format: CompressFormat.jpeg,
      keepExif: false,
    );
  }
}

/// Navigateur (développement uniquement) : pas de compression native ; le serveur
/// vérifie de toute façon la taille et le format.
class PassthroughImageCompressor implements ImageCompressor {
  const PassthroughImageCompressor();

  @override
  Future<Uint8List> compress(Uint8List original) async => original;
}

ImageCompressor platformCompressor() =>
    kIsWeb ? const PassthroughImageCompressor() : const NativeImageCompressor();
