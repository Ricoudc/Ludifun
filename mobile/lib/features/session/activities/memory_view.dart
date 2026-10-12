import 'dart:async';

import 'package:flutter/material.dart';

import '../../../app/theme.dart';
import '../../../models/account.dart';
import 'activity_registry.dart';
import 'common.dart';

/// Memory : `{prompt, cards:[{id,text,pair}]}` → `{moves:[[card_a, card_b]…]}`.
///
/// Les cartes sont retournées deux par deux ; une paire trouvée reste visible, sinon les deux
/// cartes se referment. La partie est envoyée quand toutes les paires sont trouvées.
class MemoryView extends StatefulWidget {
  const MemoryView({required this.payload, required this.onSubmit, super.key});

  static const flipBack = Duration(milliseconds: 1200);

  final Json payload;
  final ActivitySubmit onSubmit;

  @override
  State<MemoryView> createState() => _MemoryViewState();
}

typedef _Card = ({String id, String text, String pair});

class _MemoryViewState extends State<MemoryView> {
  late final List<_Card> _cards = [
    for (final c in widget.payload['cards'] as List<dynamic>)
      (id: (c as Json)['id'] as String, text: c['text'] as String, pair: c['pair'] as String),
  ];
  final _found = <String>{}; // cartes des paires trouvées
  final _open = <String>[]; // une ou deux cartes retournées
  final _moves = <List<String>>[];
  Timer? _closing;
  bool _sent = false;

  _Card _card(String id) => _cards.firstWhere((c) => c.id == id);

  void _flip(String id) {
    if (_sent || _found.contains(id) || _open.contains(id)) return;
    if (_open.length == 2) _close(); // l'enfant n'attend pas : on referme tout de suite
    setState(() => _open.add(id));
    if (_open.length < 2) return;
    final (a, b) = (_open[0], _open[1]);
    _moves.add([a, b]);
    if (_card(a).pair == _card(b).pair) {
      setState(() {
        _found.addAll([a, b]);
        _open.clear();
      });
      if (_found.length == _cards.length) _finish();
    } else {
      _closing = Timer(MemoryView.flipBack, () {
        if (mounted) setState(_close);
      });
    }
  }

  void _close() {
    _closing?.cancel();
    _closing = null;
    _open.clear();
  }

  void _finish() {
    setState(() => _sent = true);
    widget.onSubmit({'moves': _moves});
  }

  @override
  void dispose() {
    _closing?.cancel();
    super.dispose();
  }

  Widget _tile(_Card card) {
    final found = _found.contains(card.id);
    final visible = found || _open.contains(card.id);
    final color = found ? LudiColors.mastered : LudiColors.primary;
    return Semantics(
      button: !visible,
      label: visible ? card.text : 'Carte cachée',
      excludeSemantics: true,
      child: Material(
        color: visible ? color.withValues(alpha: 0.12) : LudiColors.primary,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(14),
          side: BorderSide(color: color, width: 2),
        ),
        clipBehavior: Clip.antiAlias,
        child: InkWell(
          onTap: visible ? null : () => _flip(card.id),
          child: Center(
            child: Padding(
              padding: const EdgeInsets.all(8),
              child: visible
                  ? Text(
                      card.text,
                      textAlign: TextAlign.center,
                      style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w600),
                    )
                  : const Text('?', style: TextStyle(fontSize: 30, color: Colors.white)),
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
      Prompt(widget.payload['prompt'] as String, label: 'Memory'),
      const SizedBox(height: 8),
      Text(
        '${_found.length ~/ 2} paire(s) trouvée(s) sur ${_cards.length ~/ 2} · ${_moves.length} coup(s)',
        style: const TextStyle(fontSize: 16, color: Colors.black54),
      ),
      const SizedBox(height: 16),
      GridView.count(
        crossAxisCount: _cards.length > 8 ? 3 : 2,
        shrinkWrap: true,
        physics: const NeverScrollableScrollPhysics(),
        mainAxisSpacing: 10,
        crossAxisSpacing: 10,
        childAspectRatio: 1.5,
        children: [for (final card in _cards) _tile(card)],
      ),
    ],
  );
}
