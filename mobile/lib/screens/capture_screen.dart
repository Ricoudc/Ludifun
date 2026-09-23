import 'dart:io';

import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';

import '../api/models.dart';
import '../main.dart';
import 'lesson_screen.dart';

/// Photographier une ou plusieurs pages de la leçon, puis lancer l'analyse.
class CaptureScreen extends StatefulWidget {
  final Child child;
  const CaptureScreen({super.key, required this.child});

  @override
  State<CaptureScreen> createState() => _CaptureScreenState();
}

class _CaptureScreenState extends State<CaptureScreen> {
  static const maxPages = 6;
  final _picker = ImagePicker();
  final _photos = <XFile>[];
  bool _busy = false;

  Future<void> _pick(ImageSource source) async {
    // Compression côté téléphone : lisible par l'IA, rapide à envoyer.
    final photo = await _picker.pickImage(source: source, maxWidth: 2000, imageQuality: 85);
    if (photo != null) setState(() => _photos.add(photo));
  }

  Future<void> _analyze() async {
    setState(() => _busy = true);
    try {
      final lesson = await api.createLesson(widget.child.id, _photos);
      if (!mounted) return;
      Navigator.of(context).pushReplacement(MaterialPageRoute(builder: (_) => LessonScreen(lesson: lesson)));
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('$e')));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_busy) {
      return const Scaffold(
        body: Center(
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            CircularProgressIndicator(),
            SizedBox(height: 24),
            Text('🧠 Je lis ta leçon…', style: TextStyle(fontSize: 20)),
          ]),
        ),
      );
    }
    return Scaffold(
      appBar: AppBar(title: const Text('Nouvelle révision')),
      body: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const Text('Prends ta leçon en photo, bien à plat et avec de la lumière.'),
            const SizedBox(height: 16),
            Expanded(
              child: _photos.isEmpty
                  ? const Center(child: Icon(Icons.photo_camera_outlined, size: 96))
                  : GridView.count(
                      crossAxisCount: 3,
                      mainAxisSpacing: 8,
                      crossAxisSpacing: 8,
                      children: [
                        for (final (i, p) in _photos.indexed)
                          Stack(fit: StackFit.expand, children: [
                            Image.file(File(p.path), fit: BoxFit.cover),
                            Align(
                              alignment: Alignment.topRight,
                              child: IconButton.filledTonal(
                                icon: const Icon(Icons.close, size: 16),
                                onPressed: () => setState(() => _photos.removeAt(i)),
                              ),
                            ),
                          ]),
                      ],
                    ),
            ),
            Row(children: [
              Expanded(
                child: OutlinedButton.icon(
                  onPressed: _photos.length < maxPages ? () => _pick(ImageSource.gallery) : null,
                  icon: const Icon(Icons.photo_library),
                  label: const Text('Galerie'),
                ),
              ),
              const SizedBox(width: 8),
              Expanded(
                child: FilledButton.tonalIcon(
                  onPressed: _photos.length < maxPages ? () => _pick(ImageSource.camera) : null,
                  icon: const Icon(Icons.photo_camera),
                  label: Text(_photos.isEmpty ? 'Photographier' : 'Ajouter une page'),
                ),
              ),
            ]),
            const SizedBox(height: 8),
            FilledButton(
              onPressed: _photos.isEmpty ? null : _analyze,
              child: const Padding(padding: EdgeInsets.all(12), child: Text('Analyser ma leçon')),
            ),
          ],
        ),
      ),
    );
  }
}
