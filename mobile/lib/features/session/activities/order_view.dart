import 'package:flutter/material.dart';

import '../../../app/theme.dart';
import '../../../models/account.dart';
import 'activity_registry.dart';
import 'common.dart';

/// Remettre dans l'ordre (étapes d'un processus) et frise chronologique :
/// `{prompt, items:[{id,text}]}` → `{order:[id…]}`.
///
/// L'enfant touche les étiquettes dans l'ordre ; toucher une étiquette placée la retire.
class OrderView extends StatefulWidget {
  const OrderView({
    required this.payload,
    required this.onSubmit,
    this.timeline = false,
    super.key,
  });

  final Json payload;
  final ActivitySubmit onSubmit;
  final bool timeline;

  @override
  State<OrderView> createState() => _OrderViewState();
}

class _OrderViewState extends State<OrderView> {
  late final List<Choice> _items = choicesOf(widget.payload['items']);
  final _order = <String>[];
  bool _sent = false;

  String _text(String id) => _items.firstWhere((c) => c.id == id).text;

  void _toggle(String id) =>
      setState(() => _order.contains(id) ? _order.remove(id) : _order.add(id));

  void _submit() {
    if (_sent) return;
    setState(() => _sent = true);
    widget.onSubmit({'order': List.of(_order)});
  }

  @override
  Widget build(BuildContext context) {
    final left = _items.where((c) => !_order.contains(c.id)).toList();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Prompt(
          widget.payload['prompt'] as String,
          label: widget.timeline ? 'Frise chronologique' : 'Remets dans l\'ordre',
        ),
        const SizedBox(height: 8),
        Text(
          widget.timeline
              ? 'Touche les événements du plus ancien au plus récent.'
              : 'Touche les étiquettes dans l\'ordre.',
          style: const TextStyle(fontSize: 16, color: Colors.black54),
        ),
        const SizedBox(height: 16),
        for (final (index, id) in _order.indexed)
          _Placed(
            number: index + 1,
            text: _text(id),
            timeline: widget.timeline,
            last: index == _items.length - 1,
            onTap: _sent ? null : () => _toggle(id),
          ),
        if (_order.isNotEmpty && left.isNotEmpty) const SizedBox(height: 12),
        for (final choice in left)
          Padding(
            padding: const EdgeInsets.only(bottom: 10),
            child: AnswerButton(
              label: choice.text,
              color: LudiColors.accent,
              onPressed: _sent ? null : () => _toggle(choice.id),
            ),
          ),
        const SizedBox(height: 16),
        FilledButton(
          onPressed: left.isEmpty && !_sent ? _submit : null,
          child: Text(left.isEmpty ? 'Valider' : 'Encore ${left.length} à placer'),
        ),
      ],
    );
  }
}

/// Étiquette déjà placée : son rang, et le trait de la frise.
class _Placed extends StatelessWidget {
  const _Placed({
    required this.number,
    required this.text,
    required this.timeline,
    required this.last,
    required this.onTap,
  });

  final int number;
  final String text;
  final bool timeline;
  final bool last;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) => Semantics(
    button: true,
    label: '$number : $text. Toucher pour retirer.',
    excludeSemantics: true,
    child: InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(14),
      child: IntrinsicHeight(
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            SizedBox(
              width: 40,
              child: Column(
                children: [
                  CircleAvatar(
                    radius: 16,
                    backgroundColor: LudiColors.primary,
                    foregroundColor: Colors.white,
                    child: Text('$number', style: const TextStyle(fontWeight: FontWeight.w800)),
                  ),
                  if (timeline && !last)
                    Expanded(
                      child: Container(width: 4, color: LudiColors.primary.withValues(alpha: 0.4)),
                    ),
                ],
              ),
            ),
            const SizedBox(width: 10),
            Expanded(
              child: Padding(
                padding: const EdgeInsets.only(bottom: 12, top: 4),
                child: Text(
                  text,
                  style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w600),
                ),
              ),
            ),
            const Icon(Icons.close, size: 18, color: Colors.black38),
          ],
        ),
      ),
    ),
  );
}
