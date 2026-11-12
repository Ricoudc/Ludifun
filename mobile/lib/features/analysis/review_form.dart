import 'dart:typed_data';

import 'package:flutter/material.dart';

import '../../app/theme.dart';
import '../../models/lesson.dart';

typedef ReviewAnswer = ({String itemId, String status, String? text});

/// « Peux-tu vérifier ? » : pour chaque passage mal lu, l'enfant regarde son cahier et répond
/// « c'est bien ça », écrit le bon mot, ou « je ne sais pas » (cahier des charges complet §10).
class ReviewForm extends StatefulWidget {
  const ReviewForm({
    required this.items,
    required this.onSubmit,
    this.photos = const [],
    super.key,
  });

  final List<ReviewItem> items;

  /// Photos encore sur le téléphone, pour zoomer dessus.
  final List<Uint8List> photos;
  final Future<void> Function(List<ReviewAnswer> answers) onSubmit;

  @override
  State<ReviewForm> createState() => _ReviewFormState();
}

class _ReviewFormState extends State<ReviewForm> {
  final _status = <String, String>{};
  final _fields = <String, TextEditingController>{};
  bool _sending = false;

  @override
  void dispose() {
    for (final field in _fields.values) {
      field.dispose();
    }
    super.dispose();
  }

  TextEditingController _field(String id) => _fields.putIfAbsent(id, TextEditingController.new);

  bool get _complete => widget.items.every(
    (i) => switch (_status[i.id]) {
      'corrected' => _field(i.id).text.trim().isNotEmpty,
      null => false,
      _ => true,
    },
  );

  Future<void> _submit() async {
    setState(() => _sending = true);
    await widget.onSubmit([
      for (final i in widget.items)
        (
          itemId: i.id,
          status: _status[i.id]!,
          text: _status[i.id] == 'corrected' ? _field(i.id).text.trim() : null,
        ),
    ]);
    if (mounted) setState(() => _sending = false);
  }

  void _showPhotos() => showDialog<void>(
    context: context,
    builder: (context) => Dialog.fullscreen(
      child: Stack(
        children: [
          PageView(
            children: [
              for (final photo in widget.photos)
                InteractiveViewer(maxScale: 5, child: Center(child: Image.memory(photo))),
            ],
          ),
          const Positioned(top: 8, right: 8, child: CloseButton()),
        ],
      ),
    ),
  );

  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      Text('🔍 Peux-tu vérifier ?', style: Theme.of(context).textTheme.headlineSmall),
      const SizedBox(height: 6),
      Text(
        widget.items.length > 1
            ? 'Je ne suis pas sûr d\'avoir bien lu ces mots. Regarde ton cahier.'
            : 'Je ne suis pas sûr d\'avoir bien lu ce mot. Regarde ton cahier.',
        style: const TextStyle(fontSize: 17),
      ),
      if (widget.photos.isNotEmpty)
        Align(
          alignment: Alignment.centerLeft,
          child: TextButton.icon(
            onPressed: _showPhotos,
            icon: const Icon(Icons.zoom_in),
            label: const Text('Voir ma photo'),
          ),
        ),
      const SizedBox(height: 8),
      for (final item in widget.items) _card(item),
      const SizedBox(height: 12),
      FilledButton(
        onPressed: _complete && !_sending ? _submit : null,
        style: FilledButton.styleFrom(backgroundColor: LudiColors.accent),
        child: Text(_sending ? 'Envoi…' : 'Continuer l\'analyse'),
      ),
    ],
  );

  Widget _card(ReviewItem item) {
    final status = _status[item.id];
    void choose(String value) => setState(() => _status[item.id] = value);
    final parts = item.context.split(item.readText);
    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              item.unreadable
                  ? 'Je n\'ai pas pu lire un mot ici :'
                  : 'J\'ai lu « ${item.readText} » ici :',
              style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w600),
            ),
            const SizedBox(height: 6),
            Text.rich(
              TextSpan(
                style: const TextStyle(fontSize: 18, height: 1.35),
                children: [
                  const TextSpan(text: '… '),
                  TextSpan(text: parts.first),
                  TextSpan(
                    text: item.unreadable ? '???' : item.readText,
                    style: const TextStyle(
                      fontWeight: FontWeight.w800,
                      color: LudiColors.primary,
                      decoration: TextDecoration.underline,
                    ),
                  ),
                  TextSpan(text: parts.skip(1).join(item.readText)),
                  const TextSpan(text: ' …'),
                ],
              ),
            ),
            const SizedBox(height: 12),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                if (!item.unreadable)
                  ChoiceChip(
                    label: const Text('✓ C\'est bien ça'),
                    selected: status == 'confirmed',
                    onSelected: _sending ? null : (_) => choose('confirmed'),
                  ),
                ChoiceChip(
                  label: Text(item.unreadable ? '✏️ J\'écris le mot' : '✏️ Je corrige'),
                  selected: status == 'corrected',
                  onSelected: _sending ? null : (_) => choose('corrected'),
                ),
                ChoiceChip(
                  label: const Text('🤷 Je ne sais pas'),
                  selected: status == 'unknown',
                  onSelected: _sending ? null : (_) => choose('unknown'),
                ),
              ],
            ),
            if (status == 'corrected') ...[
              const SizedBox(height: 12),
              TextField(
                controller: _field(item.id),
                autofocus: true,
                enabled: !_sending,
                maxLength: 120,
                style: const TextStyle(fontSize: 19),
                decoration: const InputDecoration(hintText: 'Le mot écrit sur ton cahier'),
                onChanged: (_) => setState(() {}),
              ),
            ],
          ],
        ),
      ),
    );
  }
}
