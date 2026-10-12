import 'package:flutter/material.dart';

import '../../../models/account.dart';
import '../../../models/figure.dart';
import 'activity_registry.dart';
import 'common.dart';
import 'figure_canvas.dart';

typedef _Paint = ({String id, String name, Color color, String colorName});

/// Coloriage (étape 22) : `{prompt, figure:{id}, palette:[{id,name,color,color_name}], count}`
/// → `{colors:[[zone_id, palette_id]…]}`.
///
/// Choisir une couleur de la légende, puis toucher les zones ; toucher une zone de la même
/// couleur l'efface. Les zones à colorier ne sont pas montrées : c'est tout l'exercice.
class ColoringView extends StatefulWidget {
  const ColoringView({required this.payload, required this.onSubmit, super.key});

  final Json payload;
  final ActivitySubmit onSubmit;

  @override
  State<ColoringView> createState() => _ColoringViewState();
}

class _ColoringViewState extends State<ColoringView> {
  late final List<_Paint> _palette = [
    for (final p in widget.payload['palette'] as List<dynamic>)
      (
        id: (p as Json)['id'] as String,
        name: p['name'] as String,
        color: parseColor(p['color']) ?? Colors.grey,
        colorName: p['color_name'] as String,
      ),
  ];
  late final int _count = widget.payload['count'] as int;
  late String _brush = _palette.first.id;
  final _colored = <String, String>{}; // zone → couleur
  bool _sent = false;

  void _paint(FigureZone zone) => setState(() {
    if (_colored[zone.id] == _brush) {
      _colored.remove(zone.id);
    } else {
      _colored[zone.id] = _brush;
    }
  });

  void _submit() {
    if (_sent) return;
    setState(() => _sent = true);
    widget.onSubmit({
      'colors': [
        for (final MapEntry(:key, :value) in _colored.entries) [key, value],
      ],
    });
  }

  @override
  Widget build(BuildContext context) {
    final colours = {for (final p in _palette) p.id: p.color};
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Prompt(widget.payload['prompt'] as String, label: '🎨 Coloriage'),
        const SizedBox(height: 8),
        Text(
          '$_count zones à colorier. ${ActivityInstruction.of(context) ?? 'Choisis une couleur, puis touche le dessin.'}',
          style: const TextStyle(fontSize: 16, color: Colors.black54),
        ),
        const SizedBox(height: 12),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: [
            for (final p in _palette)
              Semantics(
                button: true,
                selected: _brush == p.id,
                label: 'Couleur ${p.colorName} : ${p.name}',
                excludeSemantics: true,
                child: ChoiceChip(
                  avatar: CircleAvatar(backgroundColor: p.color),
                  label: Text(p.name, style: const TextStyle(fontSize: 16)),
                  selected: _brush == p.id,
                  showCheckmark: false,
                  side: BorderSide(color: p.color, width: _brush == p.id ? 3 : 1),
                  onSelected: _sent ? null : (_) => setState(() => _brush = p.id),
                ),
              ),
          ],
        ),
        const SizedBox(height: 12),
        FigureLoader(
          id: (widget.payload['figure'] as Json)['id'] as String,
          builder: (figure) => FigureCanvas(
            figure: figure,
            plain: true,
            colors: {for (final MapEntry(:key, :value) in _colored.entries) key: colours[value]!},
            onTapZone: _sent ? null : _paint,
          ),
        ),
        const SizedBox(height: 16),
        FilledButton(
          onPressed: _colored.length >= _count && !_sent ? _submit : null,
          child: Text(
            _colored.length >= _count
                ? 'J\'ai fini'
                : 'Encore ${_count - _colored.length} à colorier',
          ),
        ),
      ],
    );
  }
}
