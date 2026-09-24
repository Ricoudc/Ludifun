import 'package:flutter/material.dart';

import '../../../app/theme.dart';
import '../../../models/account.dart';
import '../../../models/figure.dart';
import 'activity_registry.dart';
import 'common.dart';
import 'figure_canvas.dart';

/// Carte (étape 22) : `{prompt, figure:{id}, items:[{id,text}]}` → `{answers:[[item_id, zone_id]…]}`.
///
/// Un nom à la fois (« Touche : Bretagne ») ; l'enfant touche la zone sur le dessin. La réponse
/// part quand tous les noms sont placés ; « Annuler » reprend le dernier.
class MapView extends StatefulWidget {
  const MapView({required this.payload, required this.onSubmit, super.key});

  final Json payload;
  final ActivitySubmit onSubmit;

  @override
  State<MapView> createState() => _MapViewState();
}

class _MapViewState extends State<MapView> {
  late final List<Choice> _items = choicesOf(widget.payload['items']);
  final _answers = <String, String>{}; // question → zone touchée
  bool _sent = false;

  Choice? get _current => _items.where((i) => !_answers.containsKey(i.id)).firstOrNull;

  void _touch(FigureZone zone) {
    final current = _current;
    if (_sent || current == null) return;
    setState(() => _answers[current.id] = zone.id);
    if (_answers.length == _items.length) {
      setState(() => _sent = true);
      widget.onSubmit({
        'answers': [
          for (final item in _items) [item.id, _answers[item.id]],
        ],
      });
    }
  }

  void _undo() => setState(() => _answers.remove(_answers.keys.last));

  @override
  Widget build(BuildContext context) {
    final current = _current;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Prompt(widget.payload['prompt'] as String, label: '🗺️ Carte'),
        const SizedBox(height: 12),
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
          decoration: BoxDecoration(
            color: LudiColors.accent.withValues(alpha: 0.15),
            borderRadius: BorderRadius.circular(14),
          ),
          child: Text(
            current == null
                ? 'C\'est fini !'
                : 'Touche : ${current.text}  (${_answers.length + 1} / ${_items.length})',
            style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w800),
          ),
        ),
        const SizedBox(height: 12),
        FigureLoader(
          id: (widget.payload['figure'] as Json)['id'] as String,
          builder: (figure) => FigureCanvas(
            figure: figure,
            colors: {
              for (final zone in _answers.values) zone: LudiColors.primary.withValues(alpha: 0.55),
            },
            onTapZone: _sent ? null : _touch,
          ),
        ),
        const SizedBox(height: 8),
        const Text(
          'Pince le dessin avec deux doigts pour zoomer.',
          style: TextStyle(fontSize: 14, color: Colors.black54),
        ),
        if (_answers.isNotEmpty && !_sent)
          Align(
            alignment: Alignment.centerRight,
            child: TextButton.icon(
              onPressed: _undo,
              icon: const Icon(Icons.undo),
              label: const Text('Annuler'),
            ),
          ),
      ],
    );
  }
}
