import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import 'package:ludifun/features/capture/image_compressor.dart';
import 'package:ludifun/features/lesson/resource_screen.dart';
import 'package:ludifun/models/resource.dart';

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

/// Photo que le téléphone ne sait pas décoder (fichier abîmé, format inconnu).
class BrokenCompressor implements ImageCompressor {
  @override
  Future<Uint8List> compress(Uint8List original) async => throw Exception('image illisible');
}

/// Compression simulée : marque les octets pour vérifier qu'elle a bien eu lieu.
class FakeCompressor implements ImageCompressor {
  @override
  Future<Uint8List> compress(Uint8List original) async =>
      Uint8List.fromList([...utf8.encode('jpeg:'), ...original.take(4)]);
}

/// Visionneuse simulée : la page affiche son adresse ; « Finir l'exercice » envoie le message
/// de score de MathALÉA (deux fois, comme la vraie page peut le faire) ; « Lien externe » tente
/// d'ouvrir un autre site.
class FakeResourcePage implements ResourcePageBuilder {
  const FakeResourcePage();

  static const scoreMessage =
      '{"action":"mathalea:score","resultsByExercice":'
      '[{"numberOfPoints":4,"numberOfQuestions":5,"uuid":"f0f0f"}]}';

  @override
  Widget build(
    LessonResource resource, {
    required ValueChanged<ResourceScore> onScore,
    required ValueChanged<Uri> onBlocked,
  }) => Column(
    children: [
      Text('Page : ${resource.url}'),
      TextButton(
        onPressed: () {
          for (var i = 0; i < 2; i++) {
            if (scoreFromMessage(scoreMessage) case final score?) onScore(score);
          }
        },
        child: const Text('Finir l\'exercice'),
      ),
      TextButton(
        onPressed: () => onBlocked(Uri.parse('https://publicite.example.com/jeu')),
        child: const Text('Lien externe'),
      ),
    ],
  );
}
