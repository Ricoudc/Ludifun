import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:share_plus/share_plus.dart';

/// Remet un fichier au parent : la feuille de partage du téléphone permet de l'enregistrer
/// (Fichiers, Google Drive…) ou de l'envoyer (e-mail…).
abstract interface class FileSharer {
  Future<void> share({
    required String filename,
    required Uint8List bytes,
    required String mimeType,
    String? subject,
  });
}

class SystemFileSharer implements FileSharer {
  const SystemFileSharer();

  @override
  Future<void> share({
    required String filename,
    required Uint8List bytes,
    required String mimeType,
    String? subject,
  }) async {
    await SharePlus.instance.share(
      ShareParams(
        files: [XFile.fromData(bytes, mimeType: mimeType, name: filename)],
        fileNameOverrides: [filename],
        subject: subject,
      ),
    );
  }
}

final fileSharerProvider = Provider<FileSharer>((ref) => const SystemFileSharer());
