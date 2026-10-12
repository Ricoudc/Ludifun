import 'package:flutter/material.dart';

import '../../../app/theme.dart';
import '../../../models/account.dart';
import 'activity_registry.dart';
import 'common.dart';

/// Ranger dans les cases : `{prompt, categories:[{id,name}], items:[{id,text}]}`
/// → `{assignments:[[item_id, category_id]…]}`.
///
/// Toucher une étiquette, puis la case où la ranger ; toucher une étiquette rangée la ressort.
class ClassifyView extends StatefulWidget {
  const ClassifyView({required this.payload, required this.onSubmit, super.key});

  final Json payload;
  final ActivitySubmit onSubmit;

  @override
  State<ClassifyView> createState() => _ClassifyViewState();
}

class _ClassifyViewState extends State<ClassifyView> {
  late final List<Choice> _items = choicesOf(widget.payload['items']);
  late final List<Choice> _categories = [
    for (final c in widget.payload['categories'] as List<dynamic>)
      (id: (c as Json)['id'] as String, text: c['name'] as String),
  ];
  final _placed = <String, String>{}; // étiquette → case
  String? _selected;
  bool _sent = false;

  void _select(String id) => setState(() => _selected = _selected == id ? null : id);

  void _drop(String category) {
    final item = _selected;
    if (item == null) return;
    setState(() {
      _placed[item] = category;
      _selected = null;
    });
  }

  void _submit() {
    if (_sent) return;
    setState(() => _sent = true);
    widget.onSubmit({
      'assignments': [
        for (final MapEntry(:key, :value) in _placed.entries) [key, value],
      ],
    });
  }

  Widget _chip(Choice item, {required bool inBox}) => Semantics(
    button: true,
    selected: _selected == item.id,
    child: ChoiceChip(
      label: Text(item.text, style: const TextStyle(fontSize: 17)),
      selected: _selected == item.id,
      showCheckmark: false,
      selectedColor: LudiColors.accent.withValues(alpha: 0.35),
      side: BorderSide(color: inBox ? LudiColors.primary : LudiColors.accent, width: 2),
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 10),
      onSelected: _sent
          ? null
          : (_) => inBox ? setState(() => _placed.remove(item.id)) : _select(item.id),
    ),
  );

  @override
  Widget build(BuildContext context) {
    final loose = _items.where((i) => !_placed.containsKey(i.id)).toList();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Prompt(widget.payload['prompt'] as String, label: 'Range dans les cases'),
        const SizedBox(height: 8),
        Text(
          _selected == null
              ? ActivityInstruction.of(context) ?? 'Touche une étiquette, puis la case où elle va.'
              : 'Maintenant, touche la bonne case.',
          style: const TextStyle(fontSize: 16, color: Colors.black54),
        ),
        const SizedBox(height: 12),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: [for (final item in loose) _chip(item, inBox: false)],
        ),
        const SizedBox(height: 16),
        for (final category in _categories)
          Padding(
            padding: const EdgeInsets.only(bottom: 12),
            child: Semantics(
              button: _selected != null,
              label: 'Case ${category.text}',
              child: Material(
                color: _selected != null
                    ? LudiColors.primary.withValues(alpha: 0.08)
                    : Colors.white,
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(16),
                  side: BorderSide(color: LudiColors.primary, width: _selected != null ? 3 : 1.5),
                ),
                clipBehavior: Clip.antiAlias,
                child: InkWell(
                  onTap: _sent || _selected == null ? null : () => _drop(category.id),
                  child: Container(
                    constraints: const BoxConstraints(minHeight: 80),
                    padding: const EdgeInsets.all(12),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          category.text,
                          style: const TextStyle(
                            fontSize: 18,
                            fontWeight: FontWeight.w800,
                            color: LudiColors.primary,
                          ),
                        ),
                        const SizedBox(height: 8),
                        Wrap(
                          spacing: 8,
                          runSpacing: 8,
                          children: [
                            for (final item in _items)
                              if (_placed[item.id] == category.id) _chip(item, inBox: true),
                          ],
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ),
          ),
        const SizedBox(height: 4),
        FilledButton(
          onPressed: loose.isEmpty && !_sent ? _submit : null,
          child: Text(loose.isEmpty ? 'Valider' : 'Encore ${loose.length} à ranger'),
        ),
      ],
    );
  }
}
