import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../../../app/theme.dart';
import '../../../models/account.dart';
import 'activity_registry.dart';
import 'common.dart';

/// Jeux de maths calculés par le serveur : droite graduée, fraction à colorier, opération posée.
/// Le dessin est fait ici à partir des nombres envoyés ; la correction reste sur le serveur.

/// Les choix d'une question « lire » (droite graduée, fraction, heure, règle) : `{choice_id}`.
class ChoiceGrid extends StatelessWidget {
  const ChoiceGrid({required this.payload, required this.onChoose, super.key});

  final Json payload;
  final void Function(String id)? onChoose;

  static const _colors = [
    LudiColors.primary,
    LudiColors.accent,
    Color(0xFF1E88E5),
    Color(0xFF8E24AA),
  ];

  @override
  Widget build(BuildContext context) => Wrap(
    spacing: 12,
    runSpacing: 12,
    alignment: WrapAlignment.center,
    children: [
      for (final (i, choice) in choicesOf(payload['choices']).indexed)
        SizedBox(
          width: 150,
          child: AnswerButton(
            label: choice.text,
            color: _colors[i % _colors.length],
            onPressed: onChoose == null ? null : () => onChoose!(choice.id),
          ),
        ),
    ],
  );
}

// --------------------------------------------------------------------------------------------
// Droite graduée : `{prompt, task:"place"|"read", intervals, labels:[{index,text}], arrow?,
// choices?}` → `{index}` ou `{choice_id}`.
// --------------------------------------------------------------------------------------------

class NumberLineView extends StatefulWidget {
  const NumberLineView({required this.payload, required this.onSubmit, super.key});

  final Json payload;
  final ActivitySubmit onSubmit;

  @override
  State<NumberLineView> createState() => _NumberLineViewState();
}

class _NumberLineViewState extends State<NumberLineView> {
  int? _touched;
  bool _sent = false;

  bool get _read => widget.payload['task'] == 'read';
  int get _intervals => (widget.payload['intervals'] as num).toInt();

  void _send(Map<String, Object?> response) {
    if (_sent) return;
    setState(() => _sent = true);
    widget.onSubmit(response);
  }

  @override
  Widget build(BuildContext context) {
    final labels = {
      for (final l in widget.payload['labels'] as List<dynamic>)
        ((l as Json)['index'] as num).toInt(): l['text'] as String,
    };
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Prompt(widget.payload['prompt'] as String, label: ActivityInstruction.of(context)),
        const SizedBox(height: 16),
        LayoutBuilder(
          builder: (context, box) {
            final margin = 24.0;
            final step = (box.maxWidth - 2 * margin) / _intervals;
            return GestureDetector(
              key: const Key('number-line'),
              behavior: HitTestBehavior.opaque,
              onTapUp: _read || _sent
                  ? null
                  : (details) {
                      final index = ((details.localPosition.dx - margin) / step).round();
                      if (index >= 0 && index <= _intervals) setState(() => _touched = index);
                    },
              child: SizedBox(
                height: 110,
                child: CustomPaint(
                  size: Size.infinite,
                  painter: _NumberLinePainter(
                    intervals: _intervals,
                    labels: labels,
                    arrow: (widget.payload['arrow'] as num?)?.toInt(),
                    touched: _touched,
                    margin: margin,
                    font: DefaultTextStyle.of(context).style,
                  ),
                ),
              ),
            );
          },
        ),
        const SizedBox(height: 16),
        if (_read)
          ChoiceGrid(
            payload: widget.payload,
            onChoose: _sent ? null : (id) => _send({'choice_id': id}),
          )
        else
          FilledButton(
            onPressed: _touched == null || _sent ? null : () => _send({'index': _touched}),
            child: const Text('Valider'),
          ),
      ],
    );
  }
}

class _NumberLinePainter extends CustomPainter {
  _NumberLinePainter({
    required this.intervals,
    required this.labels,
    required this.arrow,
    required this.touched,
    required this.margin,
    required this.font,
  });

  final int intervals;
  final Map<int, String> labels;
  final int? arrow;
  final int? touched;
  final double margin;
  final TextStyle font;

  @override
  void paint(Canvas canvas, Size size) {
    final y = size.height * 0.45;
    final step = (size.width - 2 * margin) / intervals;
    final ink = Paint()
      ..color = Colors.black87
      ..strokeWidth = 2.5;
    canvas.drawLine(Offset(margin - 8, y), Offset(size.width - margin + 8, y), ink);
    for (var i = 0; i <= intervals; i++) {
      final x = margin + i * step;
      final big = labels.containsKey(i);
      canvas.drawLine(Offset(x, y - (big ? 14 : 9)), Offset(x, y + (big ? 14 : 9)), ink);
      final text = labels[i];
      if (text != null) {
        final painter = TextPainter(
          text: TextSpan(
            text: text,
            style: font.copyWith(fontSize: 16, fontWeight: FontWeight.w700, color: Colors.black87),
          ),
          textDirection: TextDirection.ltr,
        )..layout();
        painter.paint(canvas, Offset(x - painter.width / 2, y + 18));
      }
    }
    if (touched != null) {
      canvas.drawCircle(
        Offset(margin + touched! * step, y),
        11,
        Paint()..color = LudiColors.primary,
      );
    }
    if (arrow != null) {
      final x = margin + arrow! * step;
      final path = Path()
        ..moveTo(x, y - 6)
        ..lineTo(x - 10, y - 26)
        ..lineTo(x + 10, y - 26)
        ..close();
      canvas.drawPath(path, Paint()..color = LudiColors.accent);
      canvas.drawLine(
        Offset(x, y - 26),
        Offset(x, y - 44),
        Paint()
          ..color = LudiColors.accent
          ..strokeWidth = 4,
      );
    }
  }

  @override
  bool shouldRepaint(_NumberLinePainter old) => old.touched != touched || old.arrow != arrow;
}

// --------------------------------------------------------------------------------------------
// Fraction à colorier : `{prompt, task:"color"|"read", shape:"bar"|"disc", parts, colored?,
// choices?}` → `{colored:[…]}` ou `{choice_id}`.
// --------------------------------------------------------------------------------------------

class FractionBarView extends StatefulWidget {
  const FractionBarView({required this.payload, required this.onSubmit, super.key});

  final Json payload;
  final ActivitySubmit onSubmit;

  @override
  State<FractionBarView> createState() => _FractionBarViewState();
}

class _FractionBarViewState extends State<FractionBarView> {
  late final Set<int> _colored = {
    for (final i in widget.payload['colored'] as List<dynamic>? ?? const []) (i as num).toInt(),
  };
  bool _sent = false;

  bool get _read => widget.payload['task'] == 'read';
  int get _parts => (widget.payload['parts'] as num).toInt();
  bool get _disc => widget.payload['shape'] == 'disc';

  void _send(Map<String, Object?> response) {
    if (_sent) return;
    setState(() => _sent = true);
    widget.onSubmit(response);
  }

  int? _partAt(Offset position, Size size) {
    if (!_disc) {
      final index = (position.dx / size.width * _parts).floor();
      return index >= 0 && index < _parts ? index : null;
    }
    final center = size.center(Offset.zero);
    final delta = position - center;
    if (delta.distance > size.shortestSide / 2) return null;
    // Les parts partent de midi et tournent dans le sens des aiguilles d'une montre.
    var angle = math.atan2(delta.dy, delta.dx) + math.pi / 2;
    if (angle < 0) angle += 2 * math.pi;
    return (angle / (2 * math.pi) * _parts).floor() % _parts;
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Prompt(widget.payload['prompt'] as String, label: ActivityInstruction.of(context)),
        const SizedBox(height: 16),
        Center(
          child: SizedBox(
            width: _disc ? 240 : double.infinity,
            height: _disc ? 240 : 90,
            child: LayoutBuilder(
              builder: (context, box) => GestureDetector(
                key: const Key('fraction-shape'),
                behavior: HitTestBehavior.opaque,
                onTapUp: _read || _sent
                    ? null
                    : (details) {
                        final part = _partAt(details.localPosition, box.biggest);
                        if (part == null) return;
                        setState(
                          () =>
                              _colored.contains(part) ? _colored.remove(part) : _colored.add(part),
                        );
                      },
                child: CustomPaint(
                  size: Size.infinite,
                  painter: _FractionPainter(_parts, Set.of(_colored), _disc),
                ),
              ),
            ),
          ),
        ),
        const SizedBox(height: 16),
        if (_read)
          ChoiceGrid(
            payload: widget.payload,
            onChoose: _sent ? null : (id) => _send({'choice_id': id}),
          )
        else ...[
          Text(
            'Parts coloriées : ${_colored.length} sur $_parts',
            textAlign: TextAlign.center,
            style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w700),
          ),
          const SizedBox(height: 8),
          FilledButton(
            onPressed: _sent ? null : () => _send({'colored': _colored.toList()..sort()}),
            child: const Text('Valider'),
          ),
        ],
      ],
    );
  }
}

class _FractionPainter extends CustomPainter {
  _FractionPainter(this.parts, this.colored, this.disc);

  final int parts;
  final Set<int> colored;
  final bool disc;

  @override
  void paint(Canvas canvas, Size size) {
    final fill = Paint()..color = LudiColors.accent;
    final empty = Paint()..color = Colors.white;
    final ink = Paint()
      ..color = Colors.black87
      ..style = PaintingStyle.stroke
      ..strokeWidth = 2.5;
    if (disc) {
      final rect = Rect.fromCircle(
        center: size.center(Offset.zero),
        radius: size.shortestSide / 2 - 2,
      );
      final sweep = 2 * math.pi / parts;
      for (var i = 0; i < parts; i++) {
        final start = -math.pi / 2 + i * sweep;
        canvas.drawArc(rect, start, sweep, true, colored.contains(i) ? fill : empty);
        canvas.drawArc(rect, start, sweep, true, ink);
      }
      return;
    }
    final width = size.width / parts;
    for (var i = 0; i < parts; i++) {
      final cell = Rect.fromLTWH(
        i * width + 1,
        1,
        width - 2 + (i == parts - 1 ? 0 : 2),
        size.height - 2,
      );
      canvas.drawRect(cell, colored.contains(i) ? fill : empty);
      canvas.drawRect(cell, ink);
    }
  }

  @override
  bool shouldRepaint(_FractionPainter old) =>
      old.colored.length != colored.length || !old.colored.containsAll(colored);
}

// --------------------------------------------------------------------------------------------
// Opération posée : `{prompt, operator, operands:["347","285"], boxes}` → `{result}`.
// Les chiffres s'écrivent de droite à gauche, comme sur le cahier ; les retenues sont un
// brouillon (touchées, elles affichent 1) et ne sont pas envoyées.
// --------------------------------------------------------------------------------------------

class ColumnOperationView extends StatefulWidget {
  const ColumnOperationView({required this.payload, required this.onSubmit, super.key});

  final Json payload;
  final ActivitySubmit onSubmit;

  @override
  State<ColumnOperationView> createState() => _ColumnOperationViewState();
}

class _ColumnOperationViewState extends State<ColumnOperationView> {
  String _result = ''; // chiffres écrits, les unités à droite
  final _carries = <int>{};
  bool _sent = false;

  List<String> get _operands => [
    for (final o in widget.payload['operands'] as List<dynamic>) o as String,
  ];
  int get _boxes => (widget.payload['boxes'] as num).toInt();

  void _digit(String digit) {
    if (_sent || _result.length >= _boxes) return;
    setState(() => _result = digit + _result);
  }

  void _erase() {
    if (_sent || _result.isEmpty) return;
    setState(() => _result = _result.substring(1));
  }

  Widget _cell(
    String text, {
    Color? color,
    double size = 30,
    VoidCallback? onTap,
    bool boxed = false,
  }) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        width: 36,
        height: size + 12,
        alignment: Alignment.center,
        decoration: boxed
            ? BoxDecoration(
                border: Border.all(color: LudiColors.primary, width: 2),
                borderRadius: BorderRadius.circular(6),
              )
            : null,
        child: Text(
          text,
          style: TextStyle(
            fontSize: size,
            fontWeight: FontWeight.w700,
            color: color ?? Colors.black87,
          ),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final width = _boxes;
    String pad(String s) => s.padLeft(width);
    final operator = widget.payload['operator'] as String;
    final operands = _operands;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Prompt(widget.payload['prompt'] as String, label: ActivityInstruction.of(context)),
        const SizedBox(height: 12),
        Center(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              // Retenues (brouillon).
              Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const SizedBox(width: 36),
                  for (var i = 0; i < width; i++)
                    _cell(
                      _carries.contains(i) ? '1' : '·',
                      size: 16,
                      color: _carries.contains(i) ? LudiColors.accent : Colors.black26,
                      onTap: _sent
                          ? null
                          : () => setState(
                              () => _carries.contains(i) ? _carries.remove(i) : _carries.add(i),
                            ),
                    ),
                ],
              ),
              for (final (row, operand) in operands.indexed)
                Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    _cell(row == operands.length - 1 ? operator : ''),
                    for (final char in pad(operand).split('')) _cell(char.trim()),
                  ],
                ),
              Container(width: 36.0 * (width + 1), height: 3, color: Colors.black87),
              Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const SizedBox(width: 36),
                  for (final char in pad(_result).split(''))
                    _cell(char.trim(), color: LudiColors.primary, boxed: true),
                ],
              ),
            ],
          ),
        ),
        const SizedBox(height: 8),
        const Text(
          'Commence par les unités, à droite. Touche les petits points pour noter une retenue.',
          textAlign: TextAlign.center,
          style: TextStyle(fontSize: 14, color: Colors.black54),
        ),
        const SizedBox(height: 12),
        Wrap(
          alignment: WrapAlignment.center,
          spacing: 8,
          runSpacing: 8,
          children: [
            for (final digit in '1234567890'.split(''))
              SizedBox(
                width: 56,
                height: 52,
                child: OutlinedButton(
                  onPressed: _sent ? null : () => _digit(digit),
                  child: Text(digit, style: const TextStyle(fontSize: 22)),
                ),
              ),
            SizedBox(
              width: 56,
              height: 52,
              child: OutlinedButton(
                onPressed: _sent ? null : _erase,
                child: const Icon(Icons.backspace_outlined),
              ),
            ),
          ],
        ),
        const SizedBox(height: 12),
        FilledButton(
          onPressed: _result.isEmpty || _sent
              ? null
              : () {
                  setState(() => _sent = true);
                  widget.onSubmit({'result': _result});
                },
          child: const Text('Valider'),
        ),
      ],
    );
  }
}

// --------------------------------------------------------------------------------------------
// Lire l'heure : `{prompt, hour, minute, choices}` → `{choice_id}`. L'horloge est dessinée ici.
// --------------------------------------------------------------------------------------------

class ClockView extends StatefulWidget {
  const ClockView({required this.payload, required this.onSubmit, super.key});

  final Json payload;
  final ActivitySubmit onSubmit;

  @override
  State<ClockView> createState() => _ClockViewState();
}

class _ClockViewState extends State<ClockView> {
  bool _sent = false;

  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      Prompt(widget.payload['prompt'] as String, label: ActivityInstruction.of(context)),
      const SizedBox(height: 16),
      Center(
        child: SizedBox(
          width: 240,
          height: 240,
          child: CustomPaint(
            painter: _ClockPainter(
              (widget.payload['hour'] as num).toInt(),
              (widget.payload['minute'] as num).toInt(),
              DefaultTextStyle.of(context).style,
            ),
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

class _ClockPainter extends CustomPainter {
  _ClockPainter(this.hour, this.minute, this.font);

  final int hour;
  final int minute;
  final TextStyle font;

  @override
  void paint(Canvas canvas, Size size) {
    final center = size.center(Offset.zero);
    final radius = size.shortestSide / 2 - 4;
    canvas.drawCircle(center, radius, Paint()..color = Colors.white);
    canvas.drawCircle(
      center,
      radius,
      Paint()
        ..color = Colors.black87
        ..style = PaintingStyle.stroke
        ..strokeWidth = 4,
    );
    Offset at(double turn, double length) =>
        center + Offset(math.sin(turn * 2 * math.pi), -math.cos(turn * 2 * math.pi)) * length;
    for (var tick = 0; tick < 60; tick++) {
      final big = tick % 5 == 0;
      canvas.drawLine(
        at(tick / 60, radius - (big ? 14 : 7)),
        at(tick / 60, radius - 2),
        Paint()
          ..color = Colors.black87
          ..strokeWidth = big ? 3 : 1,
      );
    }
    for (var n = 1; n <= 12; n++) {
      final painter = TextPainter(
        text: TextSpan(
          text: '$n',
          style: font.copyWith(fontSize: 20, fontWeight: FontWeight.w700, color: Colors.black87),
        ),
        textDirection: TextDirection.ltr,
      )..layout();
      painter.paint(
        canvas,
        at(n / 12, radius - 32) - Offset(painter.width / 2, painter.height / 2),
      );
    }
    // La petite aiguille avance entre deux nombres au fil des minutes.
    final hourTurn = ((hour % 12) + minute / 60) / 12;
    canvas.drawLine(
      center,
      at(hourTurn, radius * 0.5),
      Paint()
        ..color = LudiColors.primary
        ..strokeWidth = 8
        ..strokeCap = StrokeCap.round,
    );
    canvas.drawLine(
      center,
      at(minute / 60, radius - 44), // s'arrête avant les nombres
      Paint()
        ..color = LudiColors.accent
        ..strokeWidth = 5
        ..strokeCap = StrokeCap.round,
    );
    canvas.drawCircle(center, 7, Paint()..color = Colors.black87);
  }

  @override
  bool shouldRepaint(_ClockPainter old) => old.hour != hour || old.minute != minute;
}

// --------------------------------------------------------------------------------------------
// Monnaie : `{prompt, task:"count"|"pay", items:[{id,value}], choices?}` → `{choice_id}` ou
// `{selected:[id…]}`. Valeurs en centimes ; pièces rondes, billets rectangulaires.
// --------------------------------------------------------------------------------------------

String moneyLabel(int cents) {
  if (cents > 0 && cents < 100) return '$cents c';
  final euros = cents ~/ 100;
  final rest = cents % 100;
  return rest == 0 ? '$euros €' : '$euros,${rest.toString().padLeft(2, '0')} €';
}

class MoneyView extends StatefulWidget {
  const MoneyView({required this.payload, required this.onSubmit, super.key});

  final Json payload;
  final ActivitySubmit onSubmit;

  @override
  State<MoneyView> createState() => _MoneyViewState();
}

class _MoneyViewState extends State<MoneyView> {
  final _selected = <String>{};
  bool _sent = false;

  bool get _pay => widget.payload['task'] == 'pay';

  void _send(Map<String, Object?> response) {
    if (_sent) return;
    setState(() => _sent = true);
    widget.onSubmit(response);
  }

  Widget _piece(String id, int value) {
    final bill = value >= 500;
    final selected = _selected.contains(id);
    final color = bill
        ? const Color(0xFF81C784)
        : value >= 100
        ? const Color(0xFFFFD54F)
        : value >= 10
        ? const Color(0xFFFFE082)
        : const Color(0xFFBCAAA4);
    return GestureDetector(
      key: Key('piece-$id'),
      onTap: !_pay || _sent
          ? null
          : () => setState(() => selected ? _selected.remove(id) : _selected.add(id)),
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 150),
        width: bill ? 110 : 64,
        height: bill ? 60 : 64,
        alignment: Alignment.center,
        decoration: BoxDecoration(
          color: color,
          shape: bill ? BoxShape.rectangle : BoxShape.circle,
          borderRadius: bill ? BorderRadius.circular(8) : null,
          border: Border.all(
            color: selected ? LudiColors.primary : Colors.black54,
            width: selected ? 5 : 2,
          ),
        ),
        child: Text(
          moneyLabel(value),
          style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w800, color: Colors.black87),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final items = [
      for (final i in widget.payload['items'] as List<dynamic>)
        ((i as Json)['id'] as String, (i['value'] as num).toInt()),
    ];
    final paid = items.where((i) => _selected.contains(i.$1)).fold<int>(0, (s, i) => s + i.$2);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Prompt(widget.payload['prompt'] as String, label: ActivityInstruction.of(context)),
        const SizedBox(height: 16),
        Wrap(
          spacing: 10,
          runSpacing: 10,
          alignment: WrapAlignment.center,
          children: [for (final (id, value) in items) _piece(id, value)],
        ),
        const SizedBox(height: 20),
        if (_pay) ...[
          Text(
            'Tu donnes : ${moneyLabel(paid)}',
            textAlign: TextAlign.center,
            style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w700),
          ),
          const SizedBox(height: 8),
          FilledButton(
            onPressed: _selected.isEmpty || _sent
                ? null
                : () => _send({'selected': _selected.toList()..sort()}),
            child: const Text('Payer'),
          ),
        ] else
          ChoiceGrid(
            payload: widget.payload,
            onChoose: _sent ? null : (id) => _send({'choice_id': id}),
          ),
      ],
    );
  }
}
