import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:image_picker/image_picker.dart';

import '../../app/router.dart';
import '../../app/widgets.dart';
import '../../core/api/api_exception.dart';
import '../../core/session.dart';
import '../../models/homework.dart';
import '../capture/capture_controller.dart';

/// Mode devoirs (§29) : l'enfant photographie ou recopie son exercice. Ludifun l'aidera à le
/// faire, sans le faire à sa place.
class HomeworkStartScreen extends ConsumerStatefulWidget {
  const HomeworkStartScreen({super.key});

  @override
  ConsumerState<HomeworkStartScreen> createState() => _HomeworkStartScreenState();
}

class _HomeworkStartScreenState extends ConsumerState<HomeworkStartScreen> {
  final _text = TextEditingController();
  bool _sending = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _text.addListener(() => setState(() {}));
  }

  @override
  void dispose() {
    _text.dispose();
    super.dispose();
  }

  Future<void> _send(Future<Homework> Function() create) async {
    setState(() {
      _sending = true;
      _error = null;
    });
    try {
      final homework = await create();
      if (mounted) context.go(Routes.homework(homework.id));
      return;
    } on ApiException catch (error) {
      _error = error.message;
    }
    if (mounted) setState(() => _sending = false);
  }

  Future<void> _photo() async {
    final photo = await ref.read(imagePickerProvider).pickImage(source: ImageSource.camera);
    if (photo == null) return;
    final bytes = await photo.readAsBytes();
    // La photo quitte le téléphone dès qu'elle est lue (§15).
    if (!kIsWeb) {
      try {
        File(photo.path).deleteSync();
      } on FileSystemException {
        // déjà supprimée par le système
      }
    }
    final compressed = await ref.read(imageCompressorProvider).compress(bytes);
    await _send(() => ref.read(apiProvider).homeworkFromPhoto([compressed]));
  }

  @override
  Widget build(BuildContext context) {
    final text = _text.text.trim();
    return Scaffold(
      appBar: AppBar(
        leading: BackButton(onPressed: () => context.go(Routes.childHome)),
        title: const Text('Aide aux devoirs'),
      ),
      body: CenteredBody(
        top: true,
        children: [
          Text(
            'Je t\'aide à faire ton exercice, étape par étape. C\'est toi qui trouves la réponse !',
            style: Theme.of(context).textTheme.titleMedium,
          ),
          const SizedBox(height: 20),
          FilledButton.icon(
            onPressed: _sending ? null : _photo,
            icon: const Icon(Icons.photo_camera_outlined),
            label: const Text('Prendre l\'exercice en photo'),
          ),
          const SizedBox(height: 24),
          const Text('Ou recopie l\'énoncé :', style: TextStyle(fontSize: 17)),
          const SizedBox(height: 8),
          TextField(
            controller: _text,
            enabled: !_sending,
            minLines: 3,
            maxLines: 8,
            maxLength: 3000,
            decoration: const InputDecoration(
              hintText: 'Paul a 24 billes. Il en donne 16 à Léa. Combien lui en reste-t-il ?',
              border: OutlineInputBorder(),
            ),
          ),
          const SizedBox(height: 8),
          OutlinedButton(
            onPressed: _sending || text.length < 10
                ? null
                : () => _send(() => ref.read(apiProvider).homeworkFromText(text)),
            child: const Text('C\'est parti !'),
          ),
          if (_sending) ...[
            const SizedBox(height: 16),
            const Center(child: CircularProgressIndicator()),
          ],
          if (_error != null) ErrorMessage(_error!),
        ],
      ),
    );
  }
}
