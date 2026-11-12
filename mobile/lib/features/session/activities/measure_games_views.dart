import 'package:flutter/material.dart';

import '../../../app/theme.dart';
import '../../../models/account.dart';
import 'activity_registry.dart';
import 'common.dart';
import 'math_games_views.dart';

/// Mesure, symétrie et syllabes : le dessin est fait ici à partir des nombres envoyés par le
/// serveur ; la correction reste sur le serveur.

// --------------------------------------------------------------------------------------------
// Règle : `{prompt, ruler_cm, start_mm, length_mm, choices}` → `{choice_id}`.
// --------------------------------------------------------------------------------------------

class RulerView extends StatefulWidget {
  const RulerView({required this.payload, required this.onSubmit, super.key});

  final Json payload;
  final ActivitySubmit onSubmit;

  @override
  State<RulerView> createState() => _RulerViewState();
}

class _RulerViewState extends State<RulerView> {
  bool _sent = false;

  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      Prompt(widget.payload['prompt'] as String, label: ActivityInstruction.of(context)),
      const SizedBox(height: 16),
      SizedBox(
        key: const Key('ruler'),
        height: 120,
        child: CustomPaint(
          painter: RulerPainter(
            centimetres: (widget.payload['ruler_cm'] as num).toInt(),
            startMm: (widget.payload['start_mm'] as num).toInt(),
            lengthMm: (widget.payload['length_mm'] as num).toInt(),
            font: DefaultTextStyle.of(context).style,
          ),
        ),
      ),
      const SizedBox(height: 16),
      ChoiceGrid(
        payload: widget.payload,
        onChoose: _sent
            ? null
            : (id) {
                if (_sent) return; // deux touches rapides : une seule réponse
                setState(() => _sent = true);
                widget.onSubmit({'choice_id': id});
              },
      ),
    ],
  );
}

/// Une règle graduée en millimètres, et le segment rouge posé au-dessus.
class RulerPainter extends CustomPainter {
  RulerPainter({
    required this.centimetres,
    required this.startMm,
    required this.lengthMm,
    required this.font,
  });

  final int centimetres;
  final int startMm;
  final int lengthMm;
  final TextStyle font;

  static const _margin = 20.0;

  @override
  void paint(Canvas canvas, Size size) {
    final mm = (size.width - 2 * _margin) / (centimetres * 10);
    double x(int millimetre) => _margin + millimetre * mm;
    const top = 44.0;
    final body = Rect.fromLTRB(_margin - 14, top, size.width - _margin + 14, size.height - 4);
    canvas.drawRRect(
      RRect.fromRectAndRadius(body, const Radius.circular(6)),
      Paint()..color = const Color(0xFFFFF3C4),
    );
    canvas.drawRRect(
      RRect.fromRectAndRadius(body, const Radius.circular(6)),
      Paint()
        ..color = Colors.black54
        ..style = PaintingStyle.stroke
        ..strokeWidth = 1.5,
    );
    final tick = Paint()
      ..color = Colors.black87
      ..strokeWidth = 1.2;
    for (var m = 0; m <= centimetres * 10; m++) {
      final height = m % 10 == 0 ? 22.0 : (m % 5 == 0 ? 15.0 : 8.0);
      canvas.drawLine(Offset(x(m), top), Offset(x(m), top + height), tick);
      if (m % 10 == 0) {
        final label = TextPainter(
          text: TextSpan(
            text: '${m ~/ 10}',
            style: font.copyWith(fontSize: 14, fontWeight: FontWeight.w700, color: Colors.black87),
          ),
          textDirection: TextDirection.ltr,
        )..layout();
        label.paint(canvas, Offset(x(m) - label.width / 2, top + 26));
      }
    }
    // Le segment, juste au-dessus de la règle, avec un petit trait à chaque bout.
    final segment = Paint()
      ..color = const Color(0xFFE53935)
      ..strokeWidth = 6
      ..strokeCap = StrokeCap.butt;
    const y = top - 12;
    canvas.drawLine(Offset(x(startMm), y), Offset(x(startMm + lengthMm), y), segment);
    final end = Paint()
      ..color = const Color(0xFFE53935)
      ..strokeWidth = 2;
    for (final m in [startMm, startMm + lengthMm]) {
      canvas.drawLine(Offset(x(m), y - 10), Offset(x(m), top), end);
    }
  }

  @override
  bool shouldRepaint(RulerPainter old) =>
      old.startMm != startMm || old.lengthMm != lengthMm || old.centimetres != centimetres;
}

// --------------------------------------------------------------------------------------------
// Symétrie : `{prompt, width, height, axis:"vertical"|"horizontal", filled:[[x,y]…]}` →
// `{selected:[[x,y]…]}`. L'enfant touche les cases de l'autre côté de l'axe (un second toucher
// les retire), puis « Valider ».
// --------------------------------------------------------------------------------------------

class SymmetryView extends StatefulWidget {
  const SymmetryView({required this.payload, required this.onSubmit, super.key});

  final Json payload;
  final ActivitySubmit onSubmit;

  @override
  State<SymmetryView> createState() => _SymmetryViewState();
}

typedef Cell = (int, int);

class _SymmetryViewState extends State<SymmetryView> {
  late final int _width = (widget.payload['width'] as num).toInt();
  late final int _height = (widget.payload['height'] as num).toInt();
  late final bool _vertical = widget.payload['axis'] == 'vertical';
  late final Set<Cell> _filled = {
    for (final c in widget.payload['filled'] as List<dynamic>)
      (((c as List<dynamic>)[0] as num).toInt(), (c[1] as num).toInt()),
  };
  final _selected = <Cell>{};
  bool _sent = false;

  bool _mine(Cell cell) => _vertical ? cell.$1 >= _width ~/ 2 : cell.$2 >= _height ~/ 2;

  void _toggle(Cell cell) {
    if (_sent || !_mine(cell)) return;
    setState(() => _selected.contains(cell) ? _selected.remove(cell) : _selected.add(cell));
  }

  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      Prompt(widget.payload['prompt'] as String, label: ActivityInstruction.of(context)),
      const SizedBox(height: 12),
      LayoutBuilder(
        builder: (context, constraints) {
          final side = (constraints.maxWidth / _width).clamp(16.0, 36.0);
          final size = Size(side * _width, side * _height);
          return Center(
            child: GestureDetector(
              key: const Key('symmetry-grid'),
              onTapUp: _sent
                  ? null
                  : (details) => _toggle((
                      (details.localPosition.dx / side).floor().clamp(0, _width - 1),
                      (details.localPosition.dy / side).floor().clamp(0, _height - 1),
                    )),
              child: CustomPaint(
                size: size,
                painter: _GridPainter(
                  width: _width,
                  height: _height,
                  vertical: _vertical,
                  filled: _filled,
                  selected: _selected,
                ),
              ),
            ),
          );
        },
      ),
      const SizedBox(height: 12),
      Text(
        'Cases coloriées : ${_selected.length}',
        textAlign: TextAlign.center,
        style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w700),
      ),
      const SizedBox(height: 8),
      FilledButton(
        onPressed: _sent || _selected.isEmpty
            ? null
            : () {
                setState(() => _sent = true);
                final cells = _selected.toList()
                  ..sort((a, b) => a.$1 != b.$1 ? a.$1 - b.$1 : a.$2 - b.$2);
                widget.onSubmit({
                  'selected': [
                    for (final (x, y) in cells) [x, y],
                  ],
                });
              },
        child: const Text('Valider'),
      ),
    ],
  );
}

class _GridPainter extends CustomPainter {
  _GridPainter({
    required this.width,
    required this.height,
    required this.vertical,
    required this.filled,
    required this.selected,
  });

  final int width;
  final int height;
  final bool vertical;
  final Set<Cell> filled;
  final Set<Cell> selected;

  @override
  void paint(Canvas canvas, Size size) {
    final side = size.width / width;
    canvas.drawRect(Offset.zero & size, Paint()..color = Colors.white);
    void fill(Cell cell, Color color) => canvas.drawRect(
      Rect.fromLTWH(cell.$1 * side, cell.$2 * side, side, side).deflate(1),
      Paint()..color = color,
    );
    for (final cell in filled) {
      fill(cell, LudiColors.primary);
    }
    for (final cell in selected) {
      fill(cell, LudiColors.accent);
    }
    final line = Paint()
      ..color = Colors.black26
      ..strokeWidth = 1;
    for (var i = 0; i <= width; i++) {
      canvas.drawLine(Offset(i * side, 0), Offset(i * side, size.height), line);
    }
    for (var j = 0; j <= height; j++) {
      canvas.drawLine(Offset(0, j * side), Offset(size.width, j * side), line);
    }
    final axis = Paint()
      ..color = const Color(0xFFE53935)
      ..strokeWidth = 4;
    if (vertical) {
      final x = width ~/ 2 * side;
      canvas.drawLine(Offset(x, -6), Offset(x, size.height + 6), axis);
    } else {
      final y = height ~/ 2 * side;
      canvas.drawLine(Offset(-6, y), Offset(size.width + 6, y), axis);
    }
  }

  @override
  bool shouldRepaint(_GridPainter old) => true;
}

// --------------------------------------------------------------------------------------------
// Syllabes : `{prompt, items:[{id,text}]}` → `{answers:[[mot, [coupure…]]…]}`. Un mot à la
// fois : l'enfant touche entre deux lettres pour couper (un second toucher retire la coupure).
// Une coupure `n` tombe après la n-ième lettre.
// --------------------------------------------------------------------------------------------

class SyllableView extends StatefulWidget {
  const SyllableView({required this.payload, required this.onSubmit, super.key});

  final Json payload;
  final ActivitySubmit onSubmit;

  @override
  State<SyllableView> createState() => _SyllableViewState();
}

class _SyllableViewState extends State<SyllableView> {
  late final List<Choice> _words = choicesOf(widget.payload['items']);
  final _answers = <List<Object>>[];
  final _cuts = <int>{};
  bool _sent = false;

  void _next() {
    if (_sent) return;
    final word = _words[_answers.length];
    setState(() {
      _answers.add([word.id, _cuts.toList()..sort()]);
      _cuts.clear();
    });
    if (_answers.length == _words.length) {
      setState(() => _sent = true);
      widget.onSubmit({'answers': _answers});
    }
  }

  @override
  Widget build(BuildContext context) {
    final index = _sent ? _words.length - 1 : _answers.length;
    final letters = _words[index].text.split('');
    final last = index == _words.length - 1;
    final cut = StringBuffer();
    for (final (i, letter) in letters.indexed) {
      if (_cuts.contains(i)) cut.write('-');
      cut.write(letter);
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Prompt(
          widget.payload['prompt'] as String,
          label: ActivityInstruction.of(context),
          alsoRead: [_words[index].text],
        ),
        const SizedBox(height: 8),
        Text(
          'Mot ${index + 1} sur ${_words.length}',
          textAlign: TextAlign.center,
          style: const TextStyle(fontSize: 16, color: Colors.black54),
        ),
        const SizedBox(height: 16),
        FittedBox(
          fit: BoxFit.scaleDown,
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              for (final (i, letter) in letters.indexed) ...[
                if (i > 0)
                  GestureDetector(
                    key: Key('gap-$i'),
                    behavior: HitTestBehavior.opaque,
                    onTap: _sent
                        ? null
                        : () => setState(() => _cuts.contains(i) ? _cuts.remove(i) : _cuts.add(i)),
                    child: SizedBox(
                      width: 26,
                      height: 64,
                      child: Center(
                        child: Container(
                          width: _cuts.contains(i) ? 5 : 2,
                          height: _cuts.contains(i) ? 56 : 24,
                          color: _cuts.contains(i) ? const Color(0xFFE53935) : Colors.black12,
                        ),
                      ),
                    ),
                  ),
                Text(letter, style: const TextStyle(fontSize: 40, fontWeight: FontWeight.w700)),
              ],
            ],
          ),
        ),
        const SizedBox(height: 12),
        Text(
          cut.toString(),
          key: const Key('syllables-preview'),
          textAlign: TextAlign.center,
          style: const TextStyle(fontSize: 24, color: LudiColors.primary),
        ),
        const SizedBox(height: 16),
        FilledButton(
          onPressed: _sent ? null : _next,
          child: Text(last ? 'Valider' : 'Mot suivant'),
        ),
      ],
    );
  }
}
