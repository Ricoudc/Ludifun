import 'package:flutter/material.dart';

import '../../../app/theme.dart';
import '../../../models/account.dart';
import 'activity_registry.dart';

/// Association : `{left:[{id,text}], right:[{id,text}]}` → `{pairs:[[left_id,right_id]…]}`.
///
/// Toucher un élément de chaque colonne les relie ; toucher un élément relié le détache.
class MatchView extends StatefulWidget {
  const MatchView({required this.payload, required this.onSubmit, super.key});

  final Json payload;
  final ActivitySubmit onSubmit;

  @override
  State<MatchView> createState() => _MatchViewState();
}

class _MatchViewState extends State<MatchView> {
  static const _pairColors = [
    Color(0xFF5B4FE0),
    Color(0xFFFF9F1C),
    Color(0xFF2EB872),
    Color(0xFF1E88E5),
    Color(0xFFD81B60),
    Color(0xFF6D4C41),
  ];

  final _pairs = <String, String>{}; // gauche → droite
  String? _left;
  String? _right;
  bool _sent = false;

  late final List<Choice> _lefts = choicesOf(widget.payload['left']);
  late final List<Choice> _rights = choicesOf(widget.payload['right']);

  Color? _colorOfLeft(String id) {
    final index = _pairs.keys.toList().indexOf(id);
    return index < 0 ? null : _pairColors[index % _pairColors.length];
  }

  Color? _colorOfRight(String id) {
    final left = _pairs.entries.where((e) => e.value == id).firstOrNull?.key;
    return left == null ? null : _colorOfLeft(left);
  }

  void _tapLeft(String id) => setState(() {
    if (_pairs.containsKey(id)) {
      _pairs.remove(id);
      return;
    }
    _left = _left == id ? null : id;
    _link();
  });

  void _tapRight(String id) => setState(() {
    final linked = _pairs.entries.where((e) => e.value == id).firstOrNull;
    if (linked != null) {
      _pairs.remove(linked.key);
      return;
    }
    _right = _right == id ? null : id;
    _link();
  });

  void _link() {
    final (left, right) = (_left, _right);
    if (left == null || right == null) return;
    _pairs[left] = right;
    _left = _right = null;
  }

  void _submit() {
    if (_sent) return;
    setState(() => _sent = true);
    widget.onSubmit({
      'pairs': [
        for (final MapEntry(:key, :value) in _pairs.entries) [key, value],
      ],
    });
  }

  Widget _tile(
    Choice choice, {
    required bool selected,
    Color? pairColor,
    required VoidCallback onTap,
  }) {
    final color = pairColor ?? (selected ? LudiColors.primary : Colors.black26);
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Semantics(
        button: true,
        selected: selected || pairColor != null,
        child: Material(
          color:
              pairColor?.withValues(alpha: 0.18) ??
              (selected ? LudiColors.primary.withValues(alpha: 0.12) : Colors.white),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(14),
            side: BorderSide(color: color, width: selected || pairColor != null ? 3 : 1),
          ),
          clipBehavior: Clip.antiAlias,
          child: InkWell(
            onTap: _sent ? null : onTap,
            child: Container(
              constraints: const BoxConstraints(minHeight: 60),
              alignment: Alignment.centerLeft,
              padding: const EdgeInsets.all(12),
              child: Text(choice.text, style: const TextStyle(fontSize: 17)),
            ),
          ),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      Text('Relie chaque élément à sa réponse', style: Theme.of(context).textTheme.titleLarge),
      const SizedBox(height: 16),
      Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(
            child: Column(
              children: [
                for (final left in _lefts)
                  _tile(
                    left,
                    selected: _left == left.id,
                    pairColor: _colorOfLeft(left.id),
                    onTap: () => _tapLeft(left.id),
                  ),
              ],
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              children: [
                for (final right in _rights)
                  _tile(
                    right,
                    selected: _right == right.id,
                    pairColor: _colorOfRight(right.id),
                    onTap: () => _tapRight(right.id),
                  ),
              ],
            ),
          ),
        ],
      ),
      const SizedBox(height: 16),
      FilledButton(
        onPressed: _pairs.length == _lefts.length && !_sent ? _submit : null,
        child: Text(
          _pairs.length == _lefts.length
              ? 'Valider'
              : 'Encore ${_lefts.length - _pairs.length} à relier',
        ),
      ),
    ],
  );
}
