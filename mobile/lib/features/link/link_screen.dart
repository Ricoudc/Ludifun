import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/router.dart';
import '../../app/widgets.dart';
import '../../core/api/api_exception.dart';
import '../../core/session.dart';

/// Écran 0 : l'enfant saisit le code à 6 chiffres affiché sur le téléphone de son parent.
/// (Le QR code arrive à l'étape 10.)
class LinkScreen extends ConsumerStatefulWidget {
  const LinkScreen({super.key});

  @override
  ConsumerState<LinkScreen> createState() => _LinkScreenState();
}

class _LinkScreenState extends ConsumerState<LinkScreen> {
  final _code = TextEditingController();
  bool _busy = false;
  String? _error;

  @override
  void dispose() {
    _code.dispose();
    super.dispose();
  }

  static String get deviceName => kIsWeb
      ? 'Navigateur'
      : switch (defaultTargetPlatform) {
          TargetPlatform.android => 'Appareil Android',
          TargetPlatform.iOS => 'iPhone ou iPad',
          _ => 'Ordinateur',
        };

  Future<void> _submit() async {
    if (_code.text.length != 6 || _busy) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final linked = await ref.read(apiProvider).link(code: _code.text, deviceName: deviceName);
      await ref.read(sessionProvider.notifier).linked(linked); // le routeur ouvre l'espace enfant
    } on ApiException catch (error) {
      if (mounted) {
        setState(() {
          _busy = false;
          _error = error.message;
        });
        _code.clear();
      }
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(leading: BackButton(onPressed: () => context.go(Routes.start))),
    body: CenteredBody(
      children: [
        const Text('🔗', textAlign: TextAlign.center, style: TextStyle(fontSize: 56)),
        const SizedBox(height: 16),
        Text(
          'Relie ta tablette',
          textAlign: TextAlign.center,
          style: Theme.of(context).textTheme.headlineMedium,
        ),
        const SizedBox(height: 8),
        const Text(
          'Demande à ton parent le code à 6 chiffres dans son espace Ludifun.',
          textAlign: TextAlign.center,
        ),
        const SizedBox(height: 32),
        TextField(
          controller: _code,
          autofocus: true,
          enabled: !_busy,
          keyboardType: TextInputType.number,
          textAlign: TextAlign.center,
          maxLength: 6,
          style: const TextStyle(fontSize: 36, letterSpacing: 12, fontWeight: FontWeight.w700),
          inputFormatters: [FilteringTextInputFormatter.digitsOnly],
          decoration: const InputDecoration(hintText: '······', counterText: ''),
          onChanged: (value) {
            setState(() {});
            if (value.length == 6) _submit();
          },
        ),
        if (_error != null) ...[const SizedBox(height: 16), ErrorMessage(_error!)],
        const SizedBox(height: 24),
        FilledButton(
          onPressed: _code.text.length == 6 && !_busy ? _submit : null,
          child: _busy
              ? const SizedBox.square(dimension: 24, child: CircularProgressIndicator())
              : const Text('C\'est parti !'),
        ),
      ],
    ),
  );
}
