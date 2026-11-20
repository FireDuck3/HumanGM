import React from 'react';
import { createRoot } from 'react-dom/client';
import { Chess, DEFAULT_POSITION, type Color, type Move, type PieceSymbol, type Square } from 'chess.js';
import './style.css';

type Position = { initialFen: string; moves: string[] };
type Candidate = {
  uci: string;
  san: string;
  stockfish_rank: number;
  stockfish_cp: number | null;
  mate: number | null;
  loss_cp: number | null;
  maia_probability: number | null;
  maia_rank: number | null;
};
type Analysis = {
  fen: string;
  target_rating: number;
  recommended: Candidate;
  candidates: Candidate[];
  stockfish: string;
  maia: string;
  selection: 'hybrid' | 'stockfish';
  max_loss_cp: number;
};
type PracticeMatch = 'white' | 'black' | 'duel';

const START: Position = { initialFen: DEFAULT_POSITION, moves: [] };
const RATINGS = [1200, 1500, 1800, 2000, 2200, 2400, 2600, 2800, 3000];
const PRACTICE_INTERVAL_MS = 900;
const DUEL_LIMIT = 20;
const GLYPHS: Record<Color, Record<PieceSymbol, string>> = {
  w: { k: '♔', q: '♕', r: '♖', b: '♗', n: '♘', p: '♙' },
  b: { k: '♚', q: '♛', r: '♜', b: '♝', n: '♞', p: '♟' },
};
const PIECE_NAMES: Record<PieceSymbol, string> = {
  k: 'Король', q: 'Ферзь', r: 'Тура', b: 'Слон', n: 'Кінь', p: 'Пішак',
};

function restore(position: Position) {
  const game = new Chess(position.initialFen);
  for (const move of position.moves) {
    game.move({ from: move.slice(0, 2), to: move.slice(2, 4), promotion: move[4] });
  }
  return game;
}

function parsePosition(text: string, format: 'FEN' | 'PGN'): Position {
  if (format === 'FEN') return { initialFen: new Chess(text).fen(), moves: [] };
  const game = new Chess();
  game.loadPgn(text);
  const history = game.history({ verbose: true });
  if (!history.length && !game.getHeaders().FEN) throw new Error('PGN без ходів або позиції.');
  return { initialFen: history[0]?.before ?? game.fen(), moves: history.map(move => move.lan) };
}

async function requestAnalysis(position: Position, rating: number, signal: AbortSignal, useMaia = true): Promise<Analysis> {
  const response = await fetch('/api/analyze', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      initial_fen: position.initialFen, moves: position.moves, target_rating: rating, use_maia: useMaia,
    }),
    signal,
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(typeof payload?.detail === 'string' ? payload.detail
      : 'Аналіз наразі недоступний. Спробуй ще раз.');
  }
  if (!payload?.recommended || !Array.isArray(payload.candidates)) {
    throw new Error('Сервер не повернув результат аналізу.');
  }
  return payload as Analysis;
}

function evaluation(move: Candidate) {
  if (move.mate != null) return move.mate < 0 ? `−M${Math.abs(move.mate)}` : `M${move.mate}`;
  if (move.stockfish_cp == null) return '—';
  return `${move.stockfish_cp > 0 ? '+' : ''}${(move.stockfish_cp / 100).toFixed(2)}`;
}

function likelihood(move: Candidate) {
  if (move.maia_probability != null) {
    return new Intl.NumberFormat('uk-UA', { style: 'percent', maximumFractionDigits: 1 }).format(move.maia_probability);
  }
  return move.maia_rank != null ? `№${move.maia_rank}` : '—';
}

function moveStatus(game: Chess) {
  if (game.isCheckmate()) return 'Мат';
  if (game.isGameOver()) return 'Нічия';
  return `Хід ${game.turn() === 'w' ? 'білих' : 'чорних'}${game.isCheck() ? ' · шах' : ''}`;
}

function moveRows(history: Move[]) {
  const rows: { number: string; white?: string; black?: string }[] = [];
  for (const move of history) {
    const number = move.before.split(' ')[5];
    const last = rows[rows.length - 1];
    const row = last?.number === number ? last : { number };
    if (row !== last) rows.push(row);
    if (move.color === 'w') row.white = move.san;
    else row.black = move.san;
  }
  return rows;
}

function Results({ result, pending, onCopy }: {
  result: Analysis | null;
  pending: boolean;
  onCopy: (text: string, label: string) => void;
}) {
  if (!result) {
    return <section className="panel result-empty" aria-busy={pending} aria-live="polite">
      <div className="empty-symbol" aria-hidden="true">♞</div>
      <h2>{pending ? 'Рушії аналізують позицію' : 'Тут буде рекомендація'}</h2>
      <p>{pending
        ? 'Перший запуск Maia‑3 може тривати довше.'
        : 'Stockfish знайде сильні варіанти, а Maia‑3 оцінить, які з них імовірніше зіграла б людина.'}</p>
    </section>;
  }
  const move = result.recommended;
  const hybrid = result.selection === 'hybrid';
  const maiaConnected = result.maia.startsWith('connected');
  return <>
    <section className="panel recommendation" aria-live="polite">
      <p className="section-tag">{hybrid ? 'Рекомендований хід' : 'Перший вибір Stockfish'}</p>
      <div className="recommendation-row">
        <div>
          <h2>{move.san}</h2>
          <span className="uci">{move.uci.slice(0, 2)} → {move.uci.slice(2, 4)}{move.uci[4] ? ` = ${PIECE_NAMES[move.uci[4] as PieceSymbol]}` : ''}</span>
        </div>
        <button type="button" className="button subtle" onClick={() => onCopy(move.san, 'Хід')}>Копіювати хід</button>
      </div>
      <dl className="engine-metrics">
        <div><dt>Stockfish</dt><dd>{evaluation(move)} <small>№{move.stockfish_rank}</small></dd></div>
        <div><dt>Maia‑3</dt><dd>{likelihood(move)}</dd></div>
      </dl>
      <p>{hybrid
        ? 'Хід обрано серед тактично сильних варіантів з урахуванням оцінки Maia‑3.'
        : 'Для цієї позиції рекомендація спирається на Stockfish.'}</p>
      {!maiaConnected && <p className="engine-note">Оцінка Maia‑3 недоступна для цього аналізу.</p>}
    </section>
    <section className="panel candidates">
      <h2>Варіанти Stockfish</h2>
      <div className="table-wrap">
        <table>
          <thead><tr><th scope="col">№</th><th scope="col">Хід</th><th scope="col">Оцінка</th><th scope="col">Maia‑3</th></tr></thead>
          <tbody>{result.candidates.map(candidate => (
            <tr key={candidate.uci} className={candidate.uci === move.uci ? 'highlighted' : undefined}>
              <td>{candidate.stockfish_rank}</td>
              <td><strong>{candidate.san}</strong>{candidate.uci === move.uci && <span className="chosen-dot" aria-label="Рекомендовано"/>}</td>
              <td>{evaluation(candidate)}</td><td>{likelihood(candidate)}</td>
            </tr>
          ))}</tbody>
        </table>
      </div>
      <p className="table-note">Оцінка Stockfish з боку гравця, чия черга. Maia‑3 показує ймовірність людського ходу або місце в рейтингу моделі.</p>
    </section>
  </>;
}

function App({ practice }: { practice: boolean }) {
  const [position, setPosition] = React.useState<Position>(START);
  const [selected, setSelected] = React.useState<Square | null>(null);
  const [promotion, setPromotion] = React.useState<Move[]>([]);
  const [flipped, setFlipped] = React.useState(false);
  const [rating, setRating] = React.useState(2800);
  const [format, setFormat] = React.useState<'FEN' | 'PGN'>('FEN');
  const [input, setInput] = React.useState('');
  const [result, setResult] = React.useState<Analysis | null>(null);
  const [pending, setPending] = React.useState(false);
  const [error, setError] = React.useState('');
  const [notice, setNotice] = React.useState('');
  const request = React.useRef<AbortController | null>(null);
  const latestPosition = React.useRef(position);
  const practiceRequest = React.useRef<AbortController | null>(null);
  const lastPracticeRequestTime = React.useRef(-Infinity);
  const [match, setMatch] = React.useState<PracticeMatch>('white');
  const [running, setRunning] = React.useState(false);
  const [duelPlies, setDuelPlies] = React.useState(0);
  const [practiceMessage, setPracticeMessage] = React.useState('');
  const [practiceError, setPracticeError] = React.useState('');
  const [practiceFallback, setPracticeFallback] = React.useState(false);
  const game = React.useMemo(() => restore(position), [position]);
  const history = React.useMemo(() => game.history({ verbose: true }), [game]);
  const last = history[history.length - 1];
  const gameOver = game.isGameOver();
  const autoTurn = practice && running && (match === 'duel' || game.turn() === (match === 'white' ? 'w' : 'b'));
  const stockfishTurn = match === 'duel' && game.turn() === 'b';
  const legal = selected && !gameOver ? game.moves({ square: selected, verbose: true }) : [];
  const files = flipped ? 'hgfedcba' : 'abcdefgh';
  const ranks = flipped ? '12345678' : '87654321';

  React.useEffect(() => () => request.current?.abort(), []);

  React.useEffect(() => {
    if (!autoTurn || gameOver) return;
    const controller = new AbortController();
    const requestedFen = game.fen();
    practiceRequest.current = controller;
    const delay = Math.max(0, PRACTICE_INTERVAL_MS - (performance.now() - lastPracticeRequestTime.current));
    const timer = window.setTimeout(async () => {
      lastPracticeRequestTime.current = performance.now();
      try {
        const analysis = await requestAnalysis(position, rating, controller.signal, !stockfishTurn);
        if (controller.signal.aborted || practiceRequest.current !== controller || latestPosition.current !== position) return;
        if (new Chess(analysis.fen).fen() !== requestedFen) {
          throw new Error('Рушій повернув результат для іншої позиції.');
        }
        const candidate = stockfishTurn
          ? analysis.candidates.find(move => move.stockfish_rank === 1)
          : analysis.recommended;
        const legalMoves = game.moves({ verbose: true }).filter(move => move.lan === candidate?.uci);
        if (legalMoves.length !== 1) throw new Error('Рушій повернув хід, який не можна зробити у цій позиції.');

        const move = legalMoves[0];
        const next = { initialFen: position.initialFen, moves: [...position.moves, move.lan] };
        const nextGame = restore(next);
        changePosition(next, true);
        if (!stockfishTurn) setPracticeFallback(analysis.selection === 'stockfish' && !analysis.maia.startsWith('connected'));
        setPracticeMessage(`${stockfishTurn ? 'Stockfish' : 'HumanGM'} зіграв ${move.san}.`);
        if (match === 'duel') {
          const played = duelPlies + 1;
          setDuelPlies(played);
          if (played >= DUEL_LIMIT) {
            setRunning(false);
            setPracticeMessage(`Зіграно ${DUEL_LIMIT} півходів. Натисни «Запустити», щоб продовжити.`);
          }
        }
        if (nextGame.isGameOver()) {
          setRunning(false);
          setPracticeMessage(`Партію завершено. ${moveStatus(nextGame)}.`);
        }
      } catch (failure) {
        if (controller.signal.aborted || practiceRequest.current !== controller) return;
        setRunning(false);
        setPracticeMessage('Автогру призупинено.');
        setPracticeError(failure instanceof Error ? failure.message : 'Не вдалося підключитися.');
      }
    }, delay);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
      if (practiceRequest.current === controller) practiceRequest.current = null;
    };
  }, [autoTurn, gameOver, game, position, rating, stockfishTurn, match, duelPlies]);

  function cancelPracticeRequest() {
    practiceRequest.current?.abort();
    practiceRequest.current = null;
  }

  function stopPractice(message = 'Автогру зупинено.') {
    cancelPracticeRequest();
    setRunning(false);
    setPracticeError('');
    setPracticeMessage(message);
    setPracticeFallback(false);
  }

  function startPractice() {
    if (running || gameOver || promotion.length) return;
    setSelected(null);
    setPracticeMessage('');
    setPracticeError('');
    setPracticeFallback(false);
    setDuelPlies(0);
    setRunning(true);
  }

  function invalidateAnalysis() {
    request.current?.abort();
    request.current = null;
    setPending(false);
    setResult(null);
    setError('');
    setNotice('');
  }

  function changePosition(next: Position, continuePractice = false) {
    if (practice) {
      if (continuePractice) cancelPracticeRequest();
      else stopPractice(running ? 'Позиція змінилася. Запусти автогру знову.' : '');
    }
    invalidateAnalysis();
    latestPosition.current = next;
    setSelected(null);
    setPromotion([]);
    setPosition(next);
  }

  function record(move: Move) {
    if (autoTurn || latestPosition.current !== position) return;
    const next = { initialFen: position.initialFen, moves: [...position.moves, move.lan] };
    const nextGame = practice && running ? restore(next) : null;
    changePosition(next, true);
    if (nextGame?.isGameOver()) stopPractice(`Партію завершено. ${moveStatus(nextGame)}.`);
  }

  function choose(square: Square) {
    if (gameOver || promotion.length || autoTurn) return;
    const matching = legal.filter(move => move.to === square);
    if (matching.length > 1) setPromotion(matching);
    else if (matching.length) record(matching[0]);
    else setSelected(square !== selected && game.get(square)?.color === game.turn() ? square : null);
  }

  function load(event: React.FormEvent) {
    event.preventDefault();
    try {
      changePosition(parsePosition(input.trim(), format));
      setNotice(`${format} завантажено.`);
    } catch {
      setNotice(`Не вдалося прочитати ${format}. Перевір запис позиції.`);
    }
  }

  async function copy(text: string, label: string) {
    try {
      await navigator.clipboard.writeText(text);
      setNotice(`${label} скопійовано.`);
    } catch {
      setNotice(`${label}: ${text}`);
    }
  }

  async function analyze() {
    request.current?.abort();
    const controller = new AbortController();
    request.current = controller;
    setResult(null);
    setError('');
    setNotice('');
    setPending(true);
    try {
      const payload = await requestAnalysis(position, rating, controller.signal);
      if (!controller.signal.aborted) setResult(payload);
    } catch (failure) {
      if (!controller.signal.aborted) setError(failure instanceof Error ? failure.message : 'Не вдалося підключитися.');
    } finally {
      if (request.current === controller) {
        request.current = null;
        setPending(false);
      }
    }
  }

  const suggested = result?.recommended.uci ?? '';
  return <main className="shell">
    <header className="site-header">
      <div className="brand"><span className="mark" aria-hidden="true">♞</span>
        <span>HumanGM <span className="brand-secondary">Chess Lab</span></span></div>
      <nav className="mode-switch" aria-label="Режим шахів">
        <a href="/" aria-current={!practice ? 'page' : undefined}>Аналіз</a>
        <a href="/?mode=practice" aria-current={practice ? 'page' : undefined}>Автогра</a>
      </nav>
    </header>
    <div className="intro">
      <h1>{practice ? 'Тренувальна автогра' : 'Аналіз шахової позиції'}</h1>
      <p>{practice ? 'Доручи HumanGM одну сторону або запусти матч проти Stockfish на цій дошці.'
        : 'Зістав сильні ходи Stockfish із вибором, який зробила б людина.'}</p>
    </div>

    <div className="workbench">
      <section className="position-panel" aria-label="Поточна шахова позиція">
        <div className="board-heading">
          <span className="turn"><span className={`turn-dot turn-${game.turn()}`} aria-hidden="true"/> {moveStatus(game)}</span>
          <button type="button" className="button subtle" onClick={() => setFlipped(value => !value)}>Розвернути</button>
        </div>
        <div className="board-frame">
          <div className="board" aria-label="Шахова дошка">
            {Array.from(ranks, (rank, y) => Array.from(files, (file, x) => {
              const square = `${file}${rank}` as Square;
              const piece = game.get(square);
              const label = piece ? `${square} · ${PIECE_NAMES[piece.type]} · ${piece.color === 'w' ? 'білий' : 'чорний'}` : square;
              const classes = ['square', game.squareColor(square)];
              if (last?.from === square || last?.to === square) classes.push('last');
              if (suggested.slice(0, 2) === square || suggested.slice(2, 4) === square) classes.push('recommended');
              if (selected === square) classes.push('selected');
              if (legal.some(move => move.to === square)) classes.push(piece ? 'can-capture' : 'can-move');
              return <button type="button" className={classes.join(' ')} key={square} onClick={() => choose(square)} disabled={autoTurn}
                aria-label={label} aria-pressed={selected === square}>
                {piece && <span aria-hidden="true" className={`piece piece-${piece.color}`}>{GLYPHS[piece.color][piece.type]}</span>}
                {x === 0 && <span aria-hidden="true" className="coord rank">{rank}</span>}
                {y === 7 && <span aria-hidden="true" className="coord file">{file}</span>}
              </button>;
            }))}
          </div>
        </div>
        {!!promotion.length && <div className="promotion panel" role="group" aria-label="Перетворення пішака">
          <span>Перетворити пішака на</span>
          {promotion.map(move => <button type="button" className="button subtle" key={move.lan} onClick={() => record(move)}>{PIECE_NAMES[move.promotion!]}</button>)}
          <button type="button" className="button subtle" onClick={() => setPromotion([])}>Скасувати</button>
        </div>}
        <div className="board-tools">
          <button type="button" className="button subtle" onClick={() => changePosition({ ...position, moves: position.moves.slice(0, -1) })}
            disabled={!position.moves.length}>Скасувати хід</button>
          <button type="button" className="button subtle" onClick={() => changePosition(START)}>Початкова позиція</button>
          <button type="button" className="button subtle" onClick={() => copy(game.fen(), 'FEN')}>Копіювати FEN</button>
        </div>
        <details className="panel position-import">
          <summary>Імпорт FEN або PGN</summary>
          <form onSubmit={load}>
            <div className="segmented" role="group" aria-label="Формат імпорту">
              {(['FEN', 'PGN'] as const).map(value => <button type="button" key={value} className="button subtle"
                aria-pressed={format === value} onClick={() => { setFormat(value); setInput(''); }}>{value}</button>)}
            </div>
            <label htmlFor="position-input">Встав {format} сюди</label>
            <textarea id="position-input" value={input} onChange={event => setInput(event.target.value)} rows={format === 'FEN' ? 2 : 5} />
            <button className="button subtle" type="submit" disabled={!input.trim()}>Завантажити</button>
          </form>
        </details>
        {!!history.length && <details className="panel game-history">
          <summary>Запис партії</summary>
          <ol aria-label="Історія ходів">{moveRows(history).map(row => <li key={row.number}>
            <span>{row.number}.</span><strong>{row.white ?? '…'}</strong><strong>{row.black ?? ''}</strong>
          </li>)}</ol>
        </details>}
        {notice && <p className="inline-status" role="status">{notice}</p>}
      </section>
      <aside className="analysis-panel" aria-label={practice ? 'Керування автогрою' : 'Аналіз рушіїв'}>
        <section className="panel controls">
          {practice && <div className="practice-match">
            <label htmlFor="practice-match">Хто робить ходи</label>
            <select id="practice-match" value={match} onChange={event => {
              stopPractice(running ? 'Режим змінився. Запусти автогру знову.' : '');
              setMatch(event.target.value as PracticeMatch);
              setDuelPlies(0);
              setSelected(null);
              setPromotion([]);
            }}>
              <option value="white">HumanGM за білих</option>
              <option value="black">HumanGM за чорних</option>
              <option value="duel">HumanGM проти Stockfish</option>
            </select>
          </div>}
          <div className="rating-row"><label htmlFor="target-rating">Рейтинг для Maia‑3</label>
            <select id="target-rating" value={rating} onChange={event => {
              invalidateAnalysis();
              if (practice) stopPractice(running ? 'Рейтинг змінився. Запусти автогру знову.' : '');
              setRating(Number(event.target.value));
            }}>{RATINGS.map(value => <option key={value} value={value}>{value} Elo</option>)}</select>
          </div>
          {practice ? <>
            <button type="button" className="button primary" disabled={!running && (gameOver || !!promotion.length)}
              onClick={() => running ? stopPractice() : startPractice()}>{running ? 'Зупинити' : 'Запустити'}</button>
            <div className="practice-feedback" role="status" aria-live="polite">
              <p>{running ? autoTurn ? `${stockfishTurn ? 'Stockfish' : 'HumanGM'} обирає хід…` : 'Твоя черга ходити.'
                : practiceMessage || 'Вибери режим і запусти автогру.'}</p>
              {running && practiceMessage && <p className="table-note">{practiceMessage}</p>}
              {match === 'duel' && <p className="table-note">{duelPlies} / {DUEL_LIMIT} півходів за запуск. HumanGM грає білими.</p>}
            </div>
            {practiceFallback && <p className="practice-warning">На останньому ході HumanGM оцінка Maia‑3 була недоступна. Хід обрав Stockfish.</p>}
            {practiceError && <p className="error" role="alert">{practiceError}</p>}
          </> : <button type="button" className="button primary" disabled={pending || gameOver}
            onClick={analyze}>{pending ? 'Аналізую…' : 'Знайти хід'}</button>}
          {gameOver && <p className="table-note">У цій позиції партію завершено.</p>}
          {error && <p className="error" role="alert">{error}</p>}
        </section>
        {!practice && <Results result={result} pending={pending} onCopy={copy} />}
      </aside>
    </div>
    <footer className="site-footer"><a href="/downloads/maia3-uci-source.tar.gz">Код Maia‑3</a></footer>
  </main>;
}

const practice = new URLSearchParams(window.location.search).get('mode') === 'practice';
createRoot(document.getElementById('root')!).render(<React.StrictMode><App practice={practice} /></React.StrictMode>);
