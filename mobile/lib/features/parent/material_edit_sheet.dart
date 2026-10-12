import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api/api_exception.dart';
import '../../core/session.dart';
import '../../models/parent.dart';

/// Le parent choisit, parmi les éléments d'une notion, celui qu'il veut corriger lui-même.
Future<EditableElement?> pickEditable(BuildContext context, NotionContent notion) =>
    showModalBottomSheet<EditableElement>(
      context: context,
      isScrollControlled: true,
      builder: (context) => SafeArea(
        child: ConstrainedBox(
          constraints: BoxConstraints(maxHeight: MediaQuery.sizeOf(context).height * 0.8),
          child: ListView(
            shrinkWrap: true,
            padding: const EdgeInsets.symmetric(vertical: 16),
            children: [
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 24),
                child: Text(
                  'Que voulez-vous corriger ?',
                  style: Theme.of(context).textTheme.titleLarge,
                ),
              ),
              for (final element in notion.editable)
                ListTile(
                  title: Text(element.text),
                  subtitle: Text('${element.title} · ${_answerOf(element)}'),
                  trailing: const Icon(Icons.edit_outlined),
                  onTap: () => Navigator.of(context).pop(element),
                ),
            ],
          ),
        ),
      ),
    );

String _answerOf(EditableElement e) => switch (e.kind) {
  'statement' => e.isTrue == true ? 'vrai' : 'faux',
  'cloze' => e.answers.join(' / '),
  _ => e.answer ?? '',
};

/// Fenêtre de correction d'un élément (§5.59) : la notion corrigée, ou `null` si le parent
/// renonce. Rien n'est demandé à l'IA ; la progression de l'enfant n'est pas touchée.
Future<NotionContent?> editMaterial(
  BuildContext context, {
  required String childId,
  required String lessonId,
  required String knowledgeId,
  required EditableElement element,
}) => showModalBottomSheet<NotionContent>(
  context: context,
  isScrollControlled: true,
  builder: (_) => MaterialEditSheet(
    childId: childId,
    lessonId: lessonId,
    knowledgeId: knowledgeId,
    element: element,
  ),
);

class MaterialEditSheet extends ConsumerStatefulWidget {
  const MaterialEditSheet({
    required this.childId,
    required this.lessonId,
    required this.knowledgeId,
    required this.element,
    super.key,
  });

  final String childId;
  final String lessonId;
  final String knowledgeId;
  final EditableElement element;

  @override
  ConsumerState<MaterialEditSheet> createState() => _MaterialEditSheetState();
}

class _MaterialEditSheetState extends ConsumerState<MaterialEditSheet> {
  late final _text = TextEditingController(text: widget.element.text);
  late final _answer = TextEditingController(text: widget.element.answer ?? '');
  late final _wrong = [
    for (var i = 0; i < 3; i++)
      TextEditingController(
        text: i < widget.element.distractors.length ? widget.element.distractors[i] : '',
      ),
  ];
  late final _answers = TextEditingController(text: widget.element.answers.join('\n'));
  late bool _true = widget.element.isTrue ?? true;
  bool _saving = false;
  String? _error;

  String get _kind => widget.element.kind;

  @override
  void dispose() {
    for (final c in [_text, _answer, _answers, ..._wrong]) {
      c.dispose();
    }
    super.dispose();
  }

  /// « C'est la bonne réponse » : la mauvaise réponse et la bonne échangent leur place.
  void _swap(int i) => setState(() {
    final answer = _answer.text;
    _answer.text = _wrong[i].text;
    _wrong[i].text = answer;
  });

  Future<void> _save() async {
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      final notion = await ref
          .read(apiProvider)
          .editNotion(
            widget.childId,
            widget.lessonId,
            widget.knowledgeId,
            kind: _kind,
            index: widget.element.index,
            before: widget.element.text,
            text: _text.text,
            answer: switch (_kind) {
              'question' || 'pair' || 'flashcard' => _answer.text,
              _ => null,
            },
            distractors: _kind == 'question' ? [for (final c in _wrong) c.text] : null,
            answers: _kind == 'cloze'
                ? [
                    for (final line in _answers.text.split('\n'))
                      if (line.trim().isNotEmpty) line.trim(),
                  ]
                : null,
            isTrue: _kind == 'statement' ? _true : null,
          );
      if (mounted) Navigator.of(context).pop(notion);
    } on ApiException catch (error) {
      if (mounted) {
        setState(() {
          _saving = false;
          _error = error.message;
        });
      }
    }
  }

  Widget _field(
    TextEditingController controller,
    String label, {
    int maxLines = 1,
    Widget? suffix,
  }) => Padding(
    padding: const EdgeInsets.only(top: 8),
    child: TextField(
      controller: controller,
      minLines: 1,
      maxLines: maxLines,
      decoration: InputDecoration(labelText: label, suffixIcon: suffix),
    ),
  );

  @override
  Widget build(BuildContext context) => Padding(
    padding: EdgeInsets.fromLTRB(24, 24, 24, 24 + MediaQuery.viewInsetsOf(context).bottom),
    child: SingleChildScrollView(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text('Corriger moi-même', style: Theme.of(context).textTheme.titleLarge),
          Text(widget.element.title, style: const TextStyle(color: Colors.black54)),
          ...switch (_kind) {
            'question' => [
              _field(_text, 'Question', maxLines: 4),
              _field(_answer, '✅ Bonne réponse'),
              for (var i = 0; i < 3; i++)
                _field(
                  _wrong[i],
                  '✗ Mauvaise réponse ${i + 1}',
                  suffix: IconButton(
                    tooltip: 'C\'est la bonne réponse',
                    icon: const Icon(Icons.swap_vert),
                    onPressed: () => _swap(i),
                  ),
                ),
              const Padding(
                padding: EdgeInsets.only(top: 4),
                child: Text(
                  'La bonne réponse est parmi les mauvaises ? Touchez ⇅ à côté d\'elle.',
                  style: TextStyle(fontSize: 13, color: Colors.black54),
                ),
              ),
            ],
            'statement' => [
              _field(_text, 'Affirmation', maxLines: 4),
              SwitchListTile(
                contentPadding: EdgeInsets.zero,
                title: Text(_true ? 'Cette affirmation est vraie' : 'Cette affirmation est fausse'),
                value: _true,
                onChanged: (value) => setState(() => _true = value),
              ),
            ],
            'cloze' => [
              _field(_text, 'Texte à trous (le trou s\'écrit ___)', maxLines: 4),
              _field(_answers, 'Réponses acceptées (une par ligne)', maxLines: 4),
            ],
            'pair' => [_field(_text, 'Mot ou nombre'), _field(_answer, 'À relier avec')],
            _ => [_field(_text, 'Recto', maxLines: 3), _field(_answer, 'Verso', maxLines: 3)],
          },
          if (_error case final error?)
            Padding(
              padding: const EdgeInsets.only(top: 8),
              child: Text(error, style: TextStyle(color: Theme.of(context).colorScheme.error)),
            ),
          const SizedBox(height: 12),
          FilledButton(
            onPressed: _saving ? null : _save,
            child: Text(_saving ? 'Enregistrement…' : 'Enregistrer la correction'),
          ),
          const Text(
            'Les prochaines séances utiliseront la question corrigée. La progression de '
            'l\'enfant ne change pas.',
            style: TextStyle(fontSize: 13, color: Colors.black54),
          ),
        ],
      ),
    ),
  );
}
