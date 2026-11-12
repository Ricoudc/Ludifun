import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/router.dart';
import '../../app/widgets.dart';
import '../../core/api/api_exception.dart';
import '../../core/session.dart';
import '../../models/account.dart';

/// Écran 0 : l'enfant saisit le code à 6 chiffres affiché sur le téléphone de son parent,
/// ou scanne le QR code, puis confirme « C'est toi, Emma ? ».
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

  Future<void> _link({String? code, String? qrToken}) async {
    if (_busy) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    final api = ref.read(apiProvider);
    try {
      final linked = await api.link(code: code, qrToken: qrToken, deviceName: deviceName);
      if (!mounted) return;
      setState(() => _busy = false); // plus de sablier derrière la question
      if (await _confirm(linked.child)) {
        await ref.read(sessionProvider.notifier).linked(linked); // le routeur ouvre l'accueil
        return;
      }
      await api.unlinkDevice(linked.deviceToken);
      _fail('Demande un nouveau code à ton parent, sur ton profil.');
    } on ApiException catch (error) {
      _fail(error.message);
    }
  }

  void _fail(String message) {
    if (!mounted) return;
    setState(() {
      _busy = false;
      _error = message;
    });
    _code.clear();
  }

  Future<bool> _confirm(Child child) async =>
      await showDialog<bool>(
        context: context,
        barrierDismissible: false,
        builder: (context) => AlertDialog(
          title: Text('C\'est toi, ${child.displayName} ?', textAlign: TextAlign.center),
          content: Text('${child.displayName} · ${child.grade}', textAlign: TextAlign.center),
          actionsAlignment: MainAxisAlignment.center,
          actions: [
            TextButton(onPressed: () => Navigator.of(context).pop(false), child: const Text('Non')),
            FilledButton(
              onPressed: () => Navigator.of(context).pop(true),
              style: FilledButton.styleFrom(minimumSize: const Size(140, 48)),
              child: const Text('Oui, c\'est moi !'),
            ),
          ],
        ),
      ) ??
      false;

  Future<void> _scan() async {
    final value = await context.push<String>(Routes.scanQr);
    if (value != null) await _link(qrToken: value);
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(leading: BackButton(onPressed: () => context.go(Routes.start))),
    body: CenteredBody(
      children: [
        const Text('👋', textAlign: TextAlign.center, style: TextStyle(fontSize: 56)),
        const SizedBox(height: 16),
        Text(
          'Bonjour !',
          textAlign: TextAlign.center,
          style: Theme.of(context).textTheme.headlineMedium,
        ),
        const SizedBox(height: 8),
        const Text(
          'Demande le code à ton parent.',
          textAlign: TextAlign.center,
          style: TextStyle(fontSize: 18),
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
            if (value.length == 6) _link(code: value);
          },
        ),
        if (_error != null) ...[const SizedBox(height: 16), ErrorMessage(_error!)],
        const SizedBox(height: 24),
        FilledButton(
          onPressed: _code.text.length == 6 && !_busy ? () => _link(code: _code.text) : null,
          child: _busy
              ? const SizedBox.square(dimension: 24, child: CircularProgressIndicator())
              : const Text('C\'est parti !'),
        ),
        const SizedBox(height: 16),
        const Text('ou', textAlign: TextAlign.center),
        const SizedBox(height: 16),
        OutlinedButton.icon(
          onPressed: _busy ? null : _scan,
          icon: const Icon(Icons.qr_code_scanner),
          label: const Text('Scanner le QR code'),
        ),
      ],
    ),
  );
}
