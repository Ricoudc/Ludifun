import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:qr_flutter/qr_flutter.dart';

import '../../app/router.dart';
import '../../app/theme.dart';
import '../../app/widgets.dart';
import '../../core/api/api_exception.dart';
import '../../core/session.dart';
import '../../models/parent.dart';
import '../home/home_providers.dart';
import 'parent_providers.dart';

const devicePoll = Duration(seconds: 3);

/// Écran P2 : code à 6 chiffres et QR code (10 minutes, usage unique) pour lier l'appareil
/// de l'enfant. L'écran détecte la liaison.
class LinkCodeScreen extends ConsumerStatefulWidget {
  const LinkCodeScreen({required this.childId, super.key});

  final String childId;

  @override
  ConsumerState<LinkCodeScreen> createState() => _LinkCodeScreenState();
}

class _LinkCodeScreenState extends ConsumerState<LinkCodeScreen> {
  LinkCode? _code;
  String? _error;
  int? _devicesBefore;
  bool _linked = false;
  Timer? _tick;
  Timer? _poll;

  @override
  void initState() {
    super.initState();
    _newCode();
    _tick = Timer.periodic(const Duration(seconds: 1), (_) => setState(() {}));
    _poll = Timer.periodic(devicePoll, (_) => _checkDevices());
  }

  @override
  void dispose() {
    _tick?.cancel();
    _poll?.cancel();
    super.dispose();
  }

  Future<void> _newCode() async {
    setState(() {
      _code = null;
      _error = null;
    });
    final api = ref.read(apiProvider);
    try {
      _devicesBefore ??= (await api.devices(widget.childId)).length;
      final code = await api.linkCode(widget.childId);
      if (mounted) setState(() => _code = code);
    } on ApiException catch (error) {
      if (mounted) setState(() => _error = error.message);
    }
  }

  Future<void> _checkDevices() async {
    final before = _devicesBefore;
    if (before == null || _linked) return;
    try {
      final devices = await ref.read(apiProvider).devices(widget.childId);
      if (devices.length > before && mounted) {
        _poll?.cancel();
        ref.invalidate(childrenProvider);
        setState(() => _linked = true);
      }
    } on ApiException {
      // on réessaie au prochain passage
    }
  }

  @override
  Widget build(BuildContext context) {
    final child = ref.watch(childProvider(widget.childId)).value;
    final name = child?.displayName ?? 'votre enfant';
    final code = _code;
    final left = code?.expiresAt.difference(ref.watch(nowProvider)());
    final expired = left != null && left.isNegative;
    return Scaffold(
      appBar: AppBar(
        leading: BackButton(onPressed: () => context.go(Routes.childDashboard(widget.childId))),
        title: const Text('Lier un appareil'),
      ),
      body: CenteredBody(
        children: [
          if (_linked) ...[
            const Text('✅', textAlign: TextAlign.center, style: TextStyle(fontSize: 56)),
            const SizedBox(height: 12),
            Text(
              'L\'appareil de $name est lié !',
              textAlign: TextAlign.center,
              style: Theme.of(context).textTheme.headlineSmall,
            ),
            const SizedBox(height: 24),
            FilledButton(
              onPressed: () => context.go(Routes.childDashboard(widget.childId)),
              child: const Text('Terminé'),
            ),
          ] else ...[
            Text(
              'Sur la tablette ou le téléphone de $name : ouvrez Ludifun, touchez « Je suis un '
              'enfant », puis saisissez ce code ou scannez le QR code.',
              style: const TextStyle(fontSize: 17),
            ),
            const SizedBox(height: 24),
            if (_error != null)
              ErrorMessage(_error!)
            else if (code == null)
              const Center(child: CircularProgressIndicator())
            else if (expired) ...[
              const Text(
                'Ce code a expiré.',
                textAlign: TextAlign.center,
                style: TextStyle(fontSize: 18),
              ),
            ] else ...[
              Semantics(
                label: 'Code de liaison ${code.code.split('').join(' ')}',
                child: Text(
                  '${code.code.substring(0, 3)} ${code.code.substring(3)}',
                  textAlign: TextAlign.center,
                  style: const TextStyle(
                    fontSize: 48,
                    fontWeight: FontWeight.w900,
                    letterSpacing: 6,
                    color: LudiColors.primary,
                  ),
                ),
              ),
              const SizedBox(height: 16),
              Center(
                child: QrImageView(
                  data: code.qr,
                  size: 200,
                  backgroundColor: Colors.white,
                  semanticsLabel: 'QR code de liaison',
                ),
              ),
              const SizedBox(height: 12),
              Text(
                'Valable encore ${left!.inMinutes} min ${(left.inSeconds % 60).toString().padLeft(2, '0')} s · '
                'une seule utilisation',
                textAlign: TextAlign.center,
              ),
            ],
            const SizedBox(height: 20),
            OutlinedButton(onPressed: _newCode, child: const Text('Nouveau code')),
          ],
        ],
      ),
    );
  }
}
