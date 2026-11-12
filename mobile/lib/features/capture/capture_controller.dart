import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:file_picker/file_picker.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:image_picker/image_picker.dart';

import 'image_compressor.dart';

const maxPages = 6;

class CapturedPage {
  const CapturedPage({required this.bytes, this.path});

  final Uint8List bytes;

  /// Fichier temporaire créé par l'appareil photo ou la galerie (supprimé après `ready`).
  final String? path;
}

final imagePickerProvider = Provider<ImagePicker>((ref) => ImagePicker());

final imageCompressorProvider = Provider<ImageCompressor>((ref) => platformCompressor());

/// Une leçon reçue en fichier (PDF, Word, LibreOffice) : son nom et son contenu.
typedef PickedDocument = ({String name, Uint8List bytes});

/// Extensions acceptées par le serveur (`POST /v1/lessons/document`).
const documentExtensions = ['pdf', 'docx', 'odt'];

/// Plus gros fichier accepté par le serveur.
const maxDocumentBytes = 15 * 1024 * 1024;

/// Ouvre le sélecteur de fichiers du téléphone ; null si l'enfant ou le parent annule.
final documentPickerProvider = Provider<Future<PickedDocument?> Function()>(
  (ref) => () async {
    final file = await FilePicker.pickFile(
      type: FileType.custom,
      allowedExtensions: documentExtensions,
    );
    if (file == null) return null;
    return (name: file.name, bytes: await file.readAsBytes());
  },
);

/// Pages de la leçon en cours (écran 2). Gardées jusqu'à la fin de l'analyse : si la photo
/// est illisible, l'enfant revient à l'écran 2 sans tout reprendre (§3, écran 3).
final captureProvider = NotifierProvider<CaptureController, List<CapturedPage>>(
  CaptureController.new,
);

class CaptureController extends Notifier<List<CapturedPage>> {
  @override
  List<CapturedPage> build() => const [];

  int get remaining => maxPages - state.length;

  /// Leçon envoyée avec ces photos : elles sont gardées jusqu'à sa fin d'analyse.
  String? sentLessonId;

  void markSent(String lessonId) => sentLessonId = lessonId;

  /// Fin d'analyse d'une leçon : ses photos quittent le téléphone (§15), et seulement elles.
  void analysisFinished(String lessonId) {
    if (sentLessonId == lessonId) clear();
  }

  Future<void> takePhoto() async {
    if (remaining <= 0) return;
    final photo = await ref.read(imagePickerProvider).pickImage(source: ImageSource.camera);
    if (photo != null) await _add([photo]);
  }

  Future<void> pickFromGallery() async {
    if (remaining <= 0) return;
    final photos = await ref.read(imagePickerProvider).pickMultiImage(limit: remaining);
    await _add(photos.take(remaining));
  }

  Future<void> _add(Iterable<XFile> files) async {
    sentLessonId = null; // de nouvelles photos : une nouvelle leçon
    final pages = [
      for (final file in files)
        CapturedPage(bytes: await file.readAsBytes(), path: kIsWeb ? null : file.path),
    ];
    state = [...state, ...pages].take(maxPages).toList();
  }

  void remove(int index) {
    _deleteFile(state[index]);
    state = [...state]..removeAt(index);
  }

  /// Glisser-déposer : `to` est la position finale de la page.
  void move(int from, int to) {
    final pages = [...state];
    pages.insert(to, pages.removeAt(from));
    state = pages;
  }

  /// Pages compressées, prêtes à l'envoi.
  Future<List<Uint8List>> compressed() async {
    final compressor = ref.read(imageCompressorProvider);
    return [for (final page in state) await compressor.compress(page.bytes)];
  }

  /// Après `ready` (ou abandon) : les photos quittent aussi le téléphone (§15).
  void clear() {
    state.forEach(_deleteFile);
    state = const [];
    sentLessonId = null;
  }

  static void _deleteFile(CapturedPage page) {
    final path = page.path;
    if (path == null) return;
    try {
      File(path).deleteSync();
    } on FileSystemException {
      // déjà supprimé par le système
    }
  }
}
