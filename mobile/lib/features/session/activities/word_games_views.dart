import 'package:flutter/material.dart';

import '../../../app/theme.dart';
import '../../../models/account.dart';
import 'activity_registry.dart';
import 'common.dart';

/// Jeux calculés par le serveur pour toutes les matières : chasse aux mots, conjugaison,
/// homophones. La correction reste sur le serveur.

/// Une étiquette à toucher (mot, forme d'un verbe).
class _Tag extends StatelessWidget {
  const _Tag({required this.text, required this.selected, this.onTap});

  final String text;
  final bool selected;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) => Semantics(
    button: true,
    selected: selected,
    child: Material(
      color: selected ? LudiColors.primary : LudiColors.primary.withValues(alpha: 0.08),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(14),
        side: const BorderSide(color: LudiColors.primary, width: 2),
      ),
      child: InkWell(
        borderRadius: BorderRadius.circular(14),
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
          child: Text(
            text,
            style: TextStyle(
              fontSize: 20,
              fontWeight: FontWeight.w700,
              color: selected ? Colors.white : Colors.black87,
            ),
          ),
        ),
      ),
    ),
  );
}

// --------------------------------------------------------------------------------------------
// Chasse aux mots : `{prompt, words:[{id,text}]}` → `{selected:[id…]}`.
// --------------------------------------------------------------------------------------------

class WordHuntView extends StatefulWidget {
  const WordHuntView({required this.payload, required this.onSubmit, super.key});

  final Json payload;
  final ActivitySubmit onSubmit;

  @override
  State<WordHuntView> createState() => _WordHuntViewState();
}

class _WordHuntViewState extends State<WordHuntView> {
  final _selected = <String>{};
  bool _sent = false;

  @override
  Widget build(BuildContext context) {
    final words = choicesOf(widget.payload['words']);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Prompt(widget.payload['prompt'] as String, label: ActivityInstruction.of(context)),
        const SizedBox(height: 20),
        Wrap(
          spacing: 10,
          runSpacing: 10,
          alignment: WrapAlignment.center,
          children: [
            for (final word in words)
              _Tag(
                text: word.text,
                selected: _selected.contains(word.id),
                onTap: _sent
                    ? null
                    : () => setState(
                        () => _selected.contains(word.id)
                            ? _selected.remove(word.id)
                            : _selected.add(word.id),
                      ),
              ),
          ],
        ),
        const SizedBox(height: 20),
        FilledButton(
          onPressed: _selected.isEmpty || _sent
              ? null
              : () {
                  setState(() => _sent = true);
                  widget.onSubmit({'selected': _selected.toList()..sort()});
                },
          child: const Text('Valider'),
        ),
      ],
    );
  }
}

// --------------------------------------------------------------------------------------------
// Conjugaison : `{prompt, word, items:[{id,text}], choices:[{id,text}]}` →
// `{answers:[[ligne, forme]…]}`. On touche une forme : elle va sur la première ligne vide ;
// on touche une ligne remplie : elle se vide.
// --------------------------------------------------------------------------------------------

class ConjugationView extends StatefulWidget {
  const ConjugationView({required this.payload, required this.onSubmit, super.key});

  final Json payload;
  final ActivitySubmit onSubmit;

  @override
  State<ConjugationView> createState() => _ConjugationViewState();
}

class _ConjugationViewState extends State<ConjugationView> {
  late final List<Choice> _rows = choicesOf(widget.payload['items']);
  late final List<Choice> _chips = choicesOf(widget.payload['choices']);
  // « Trouve le bon pronom » (PRONOUN) : la case vient avant la forme (« ___ allons »).
  late final bool _blankFirst = widget.payload['blank_first'] == true;
  final _placed = <String, String>{}; // ligne → forme
  bool _sent = false;

  String? get _nextRow => _rows.where((r) => !_placed.containsKey(r.id)).firstOrNull?.id;

  void _place(String chip) {
    final row = _nextRow;
    if (_sent || row == null) return;
    setState(() => _placed[row] = chip);
  }

  @override
  Widget build(BuildContext context) {
    final texts = {for (final c in _chips) c.id: c.text};
    final used = _placed.values.toSet();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Prompt(widget.payload['prompt'] as String, label: ActivityInstruction.of(context)),
        const SizedBox(height: 16),
        for (final row in _rows)
          Padding(
            padding: const EdgeInsets.only(bottom: 8),
            child: Row(
              textDirection: _blankFirst ? TextDirection.rtl : TextDirection.ltr,
              children: [
                SizedBox(
                  width: _blankFirst ? 110 : 72,
                  child: Text(
                    row.text,
                    textAlign: _blankFirst ? TextAlign.left : TextAlign.right,
                    textDirection: TextDirection.ltr,
                    style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w700),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: GestureDetector(
                    onTap: _sent || !_placed.containsKey(row.id)
                        ? null
                        : () => setState(() => _placed.remove(row.id)),
                    child: Container(
                      height: 48,
                      alignment: Alignment.centerLeft,
                      padding: const EdgeInsets.symmetric(horizontal: 12),
                      decoration: BoxDecoration(
                        color: _placed.containsKey(row.id)
                            ? LudiColors.primary.withValues(alpha: 0.12)
                            : Colors.white,
                        border: Border.all(
                          color: row.id == _nextRow ? LudiColors.accent : Colors.black26,
                          width: row.id == _nextRow ? 3 : 1.5,
                        ),
                        borderRadius: BorderRadius.circular(10),
                      ),
                      child: Text(
                        texts[_placed[row.id]] ?? '',
                        style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w600),
                      ),
                    ),
                  ),
                ),
              ],
            ),
          ),
        const SizedBox(height: 12),
        Wrap(
          spacing: 10,
          runSpacing: 10,
          alignment: WrapAlignment.center,
          children: [
            for (final chip in _chips)
              if (!used.contains(chip.id))
                _Tag(text: chip.text, selected: false, onTap: _sent ? null : () => _place(chip.id)),
          ],
        ),
        const SizedBox(height: 16),
        FilledButton(
          onPressed: _placed.length < _rows.length || _sent
              ? null
              : () {
                  setState(() => _sent = true);
                  widget.onSubmit({
                    'answers': [
                      for (final row in _rows) [row.id, _placed[row.id]],
                    ],
                  });
                },
          child: const Text('Valider'),
        ),
      ],
    );
  }
}

// --------------------------------------------------------------------------------------------
// Homophones : `{prompt, items:[{id,text,choices:[…]}]}` → `{answers:[[phrase, mot]…]}`.
// Une phrase à la fois ; la réponse part après la dernière.
// --------------------------------------------------------------------------------------------

class HomophoneView extends StatefulWidget {
  const HomophoneView({required this.payload, required this.onSubmit, super.key});

  final Json payload;
  final ActivitySubmit onSubmit;

  @override
  State<HomophoneView> createState() => _HomophoneViewState();
}

class _HomophoneViewState extends State<HomophoneView> {
  late final List<Json> _items = [
    for (final i in widget.payload['items'] as List<dynamic>) i as Json,
  ];
  final _answers = <List<String>>[];

  void _choose(String word) {
    if (_answers.length >= _items.length) return;
    setState(() => _answers.add([_items[_answers.length]['id'] as String, word]));
    if (_answers.length == _items.length) widget.onSubmit({'answers': _answers});
  }

  @override
  Widget build(BuildContext context) {
    final done = _answers.length >= _items.length;
    final item = done ? _items.last : _items[_answers.length];
    final sentence = item['text'] as String;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Prompt(
          widget.payload['prompt'] as String,
          label: ActivityInstruction.of(context),
          alsoRead: [sentence.replaceAll('___', '…')],
        ),
        const SizedBox(height: 8),
        Text(
          'Phrase ${done ? _items.length : _answers.length + 1} sur ${_items.length}',
          textAlign: TextAlign.center,
          style: const TextStyle(fontSize: 16, color: Colors.black54),
        ),
        const SizedBox(height: 16),
        Container(
          padding: const EdgeInsets.all(20),
          decoration: BoxDecoration(
            color: Colors.white,
            borderRadius: BorderRadius.circular(16),
            border: Border.all(color: Colors.black12),
          ),
          child: Text(
            sentence.replaceAll('___', '_____'),
            textAlign: TextAlign.center,
            style: const TextStyle(fontSize: 24, fontWeight: FontWeight.w600, height: 1.4),
          ),
        ),
        const SizedBox(height: 20),
        Row(
          children: [
            for (final (i, word) in (item['choices'] as List<dynamic>).cast<String>().indexed) ...[
              if (i > 0) const SizedBox(width: 12),
              Expanded(
                child: AnswerButton(
                  label: word,
                  color: i == 0 ? LudiColors.primary : LudiColors.accent,
                  onPressed: done ? null : () => _choose(word),
                ),
              ),
            ],
          ],
        ),
      ],
    );
  }
}
