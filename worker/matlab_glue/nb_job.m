function nb_job(jobfile)
%NB_JOB Glue between the NoiseBox worker and the validated core in matlab/core.
%   Reads job.json (written by the ArcGIS toolbox), calls run_field_3d / run_case_3d /
%   run_acoustic_case / nb_adiv / nb_aatm / nb_energy_sum / nb_compliance, and writes raw
%   float64 result files plus glue_result.json (manifest). NO acoustic formula lives here:
%   this file decodes inputs, loops over sources and receiver chunks, picks the dominant source
%   per receiver (a comparison of dB values) and writes outputs.
job = jsondecode(fileread(jobfile));
switch job.action
    case 'check',  do_check(job);
    case 'field',  do_field(job);
    case 'points', do_points(job);
    case 'material', do_material(job);
    case 'atmosphere', do_atmosphere(job);
    otherwise, error('nb_job:action', 'Unknown action "%s".', job.action);
end
end

% ------------------------------------------------------------------ helpers
function base = make_base(job)
G = job.G;
base.G = struct('Gs', G, 'Gm', G, 'Gr', G);
base.atm = struct('T_C', job.atm.T_C, 'RH', job.atm.RH, 'p_kPa', job.atm.p_kPa);
base.mode = job.mode;
if isfield(job, 'Gadv') && ~isempty(job.Gadv)                  % separate source / middle / receiver ground factors
    base.G = struct('Gs', job.Gadv.Gs, 'Gm', job.Gadv.Gm, 'Gr', job.Gadv.Gr);
end
if isfield(job, 'C0') && ~isempty(job.C0)                      % long-term meteorological correction (core nb_cmet)
    base.C0 = double(job.C0);
end
end

function m = decode_mat(j)
% Material from JSON -> struct for nb_material('resolve'); null / [] entries are left out.
m = struct();
names = {'surface_mass', 'volume_density', 'thickness', 'solid', 'TL', 'openness', 'tl_model'};
for i = 1:numel(names)
    n = names{i};
    if isfield(j, n) && ~isempty(j.(n))
        v = j.(n);
        if strcmp(n, 'TL'), v = double(v(:)'); end
        m.(n) = v;
    end
end
end

function [SRC, enc] = prep_sources(job)
% Per source: effective Lw (after an enclosure, if any) and directivity correction Dc. The enclosure and
% mass-law maths are the core's (nb_enclosure_surfaces / nb_enclosure / nb_material); this only decodes.
NS = numel(job.sources);
SRC = struct('x', cell(1, NS), 'y', [], 'h', [], 'Lw', [], 'Dc', []);
enc = cell(1, NS);
for s = 1:NS
    S = job.sources(s);
    SRC(s).x = S.x;  SRC(s).y = S.y;  SRC(s).h = S.h;
    SRC(s).Lw = double(S.Lw(:)');
    SRC(s).Dc = zeros(1, 8);
    if isfield(S, 'Dc') && ~isempty(S.Dc), SRC(s).Dc = double(S.Dc(:)'); end
    if isfield(S, 'enclosure') && ~isempty(S.enclosure)
        E = S.enclosure;
        sf = E.surfaces;
        if iscell(sf), sf = [sf{:}]; end
        surf = struct('name', {}, 'area', {}, 'mat', {}, 'alpha', {});
        for q = 1:numel(sf)
            surf(q).name = sf(q).name;  surf(q).area = sf(q).area;
            surf(q).mat = decode_mat(sf(q).mat);  surf(q).alpha = double(sf(q).alpha(:)');
        end
        so = 0;  if isfield(E, 'S_open') && ~isempty(E.S_open), so = E.S_open; end
        r = nb_enclosure_surfaces(SRC(s).Lw, surf, so);
        SRC(s).Lw = r.Lw_out;
        enc{s} = r;
    end
end
end

function dem = read_dem(job)
d = job.dem;
fid = fopen(fullfile(job.work_dir, 'dem.bin'), 'r');
if fid < 0, error('nb_job:dem', 'dem.bin missing'); end
Z = fread(fid, Inf, 'float64');  fclose(fid);
dem = struct('x0', d.x0, 'y0', d.y0, 'cs', d.cs, 'Z', reshape(Z, d.ny, d.nx));
end

function obs = read_obstacles(job)
obs = {};
if isempty(job.obstacles), return; end
L = job.obstacles;
if iscell(L), L = [L{:}]; end
for k = 1:numel(L)
    o = L(k);
    s = struct('x', o.x(:)', 'y', o.y(:)');
    if isfield(o, 'top') && ~isempty(o.top), s.top = o.top; else, s.h = o.h; end   % absolute top or height above ground
    if isfield(o, 'gap') && ~isempty(o.gap), s.gap = o.gap; end
    if isfield(o, 'mat') && ~isempty(o.mat), s.mat = decode_mat(o.mat); end         % transmission through the screen
    obs{end+1} = s; %#ok<AGROW>
end
end

function lim = read_limits(job)
lim = [];
if ~isfield(job, 'limits') || isempty(job.limits), return; end
L = job.limits;
bands = nan(1, 8);
set = logical(L.bands_set(:)');
v = double(L.bands(:)');
bands(set) = v(set);
lim.bands = bands;
lim.weighting = L.weighting;
lim.overallA = [];
if L.has_overall, lim.overallA = double(L.overall); end
end

function wprog(job, done, total, msg)
fid = fopen(fullfile(job.work_dir, 'progress.json'), 'w');
if fid > 0
    fprintf(fid, '{"done": %d, "total": %d, "msg": "%s"}', done, total, msg);  fclose(fid);
end
end

function wbin(job, name, A)
fid = fopen(fullfile(job.work_dir, ['out_' name '.bin']), 'w');
fwrite(fid, A, 'float64');  fclose(fid);
end

function wjson(job, S)
fid = fopen(fullfile(job.work_dir, 'glue_result.json'), 'w');
fwrite(fid, jsonencode(S), 'char');  fclose(fid);
end

function write_all(job, R, arrays)
% arrays: struct name -> N x k matrix. Written column-major; manifest lists the widths.
names = fieldnames(arrays);
man = struct();
for i = 1:numel(names)
    A = arrays.(names{i});
    wbin(job, names{i}, A);
    man.(names{i}) = size(A, 2);
end
R.arrays = man;
R.fingerprint = nb_fingerprint();
wjson(job, R);
end

function A = aatm_for(d, base)
% Atmospheric absorption for a distance vector, from the core (same branch run_acoustic_case uses).
A = nan(numel(d), 8);
ok = isfinite(d);
if ~any(ok), return; end
if strcmp(base.mode, 'iso1996')
    for k = find(ok(:))'
        A(k, :) = nb_aatm_1996(d(k), base.atm.T_C, base.atm.RH);
    end
else
    A(ok, :) = nb_aatm(d(ok), base.atm.T_C, base.atm.RH, base.atm.p_kPa);
end
end

function C = compliance_arrays(Lp, LpA, lim)
c = nb_compliance(Lp, LpA, lim);
C.code = c.code;                      % 1 pass, 0 fail, NaN no data, -1 no limits
C.margin_overall = c.overallMargin;   % dB(A) broadband minus overall limit (NaN if none)
C.worst_band = c.worstBand;           % index 1..8 of the worst exceeding band, 0 = none
C.worst_margin = c.worstMargin;       % -Inf when no band has a limit
C.margin_bands = c.margin;            % N x 8, NaN where no band limit
C.worst_margin(~isfinite(C.worst_margin)) = NaN;
end

% ------------------------------------------------------------------ check
function do_check(job)
c.Lw = 90*ones(1,8);  c.hs = 1;  c.hr = 1.5;  c.dp = 100;
c.G = struct('Gs', 0.5, 'Gm', 0.5, 'Gr', 0.5);
c.atm = struct('T_C', 15, 'RH', 70, 'p_kPa', 101.325);
c.mode = 'iso2024';
o = run_acoustic_case(c);
S.smoke = struct('case', 'Lw=90 dB each band, hs=1, hr=1.5, dp=100 m, G=0.5, 15 C, 70 %, iso2024', ...
    'LpA_broadband', o.LpA_broadband, 'Lp_broadband', o.Lp_broadband);
S.fingerprint = nb_fingerprint();
wjson(job, S);
end

% ------------------------------------------------------------------ grid
function do_field(job)
base = make_base(job);
dem = read_dem(job);
obs = read_obstacles(job);
lim = read_limits(job);
g = job.grid;
NX = g.nx;  NY = g.ny;  NP = NX*NY;
xg = g.x0 + (0:NX-1)*g.cs;
yg = g.y0 + (0:NY-1)*g.cs;
NS = numel(job.sources);
[SRC, enc] = prep_sources(job);
detail = strcmp(job.detail, 'full');
needBands = job.want_bands || detail || ~isempty(lim);
active = job.active_rows(:)';                       % 1-based grid rows to compute (rows outside the area are skipped)
if isempty(active), active = 1:NY; end
chunk = max(1, min(numel(active), job.chunk_rows));
nChunks = ceil(numel(active)/chunk);

A.LAeq = nan(NP, 1);
if needBands, A.Lp = nan(NP, 8); A.LpA = nan(NP, 8); A.LZ = nan(NP, 1); end
if detail
    A.Adiv = nan(NP, 8); A.Aatm = nan(NP, 8); A.Agr = nan(NP, 8); A.Abar = nan(NP, 8);
    A.dom = nan(NP, 1); A.kind = nan(NP, 1); A.ground = nan(NP, 1); A.dist = nan(NP, 1);
end
if ~isempty(lim)
    A.code = nan(NP, 1); A.margin_overall = nan(NP, 1); A.worst_band = nan(NP, 1);
    A.worst_margin = nan(NP, 1); A.margin_bands = nan(NP, 8);
end
closure = 0;
total = nChunks*NS;  done = 0;
wprog(job, 0, total, 'start');
for ci = 1:nChunks
    rows = active((ci-1)*chunk+1 : min(ci*chunk, numel(active)));
    idx = reshape(((rows(:)-1)*NX + (1:NX)).', [], 1);
    [XX, YY] = meshgrid(xg, yg(rows));
    xv = reshape(XX.', [], 1);  yv = reshape(YY.', [], 1);
    for s = 1:NS
        S = SRC(s);
        c = base;
        c.dem = dem;
        c.source = struct('x', S.x, 'y', S.y, 'h', S.h);
        c.Lw = S.Lw;                                           % after the enclosure, if the source has one
        c.Dc = S.Dc;                                           % directivity correction, 1x8 dB
        c.grid = struct('x', xg, 'y', yg(rows));
        c.hr = job.hr;
        c.obstacles = obs;
        o = run_field_3d(c);
        cLA = nb_energy_sum(o.LpA, 2);                         % this source alone, dB(A)
        if detail
            dp = hypot(xv - S.x, yv - S.y);
            dd = sqrt(dp.^2 + ((o.ground + job.hr) - (o.sourceGround + S.h)).^2);   % true 3D distance
            sAdiv = nan(numel(dd), 8);  okd = isfinite(dd) & dd > 0;
            sAdiv(okd, :) = nb_adiv(dd(okd)) * ones(1, 8);
            sAatm = aatm_for(dd, base);
            if NS == 1
                res = o.Lp - ((c.Lw + c.Dc) - (sAdiv + sAatm + o.Agr + o.Abar));
                closure = max(closure, max(abs(res(:)), [], 'omitnan'));
            end
        end
        if s == 1
            accLp = o.Lp;  accLpA = o.LpA;  best = cLA;  domv = ones(size(cLA));
            if detail
                dAdiv = sAdiv; dAatm = sAatm; dAgr = o.Agr; dAbar = o.Abar; dkind = o.kind; ddist = dd;
            end
        else
            accLp  = nb_energy_sum(cat(3, accLp,  o.Lp),  3);   % sources add by energy
            accLpA = nb_energy_sum(cat(3, accLpA, o.LpA), 3);
            upd = isnan(best) | (cLA > best);
            best(upd) = cLA(upd);  domv(upd) = s;
            if detail
                dAdiv(upd,:) = sAdiv(upd,:); dAatm(upd,:) = sAatm(upd,:); dAgr(upd,:) = o.Agr(upd,:);
                dAbar(upd,:) = o.Abar(upd,:); dkind(upd) = o.kind(upd); ddist(upd) = dd(upd);
            end
        end
        done = done + 1;
        wprog(job, done, total, sprintf('rows %d-%d of %d, source %d of %d', rows(1), rows(end), NY, s, NS));
    end
    LA = nb_energy_sum(accLpA, 2);                              % 8 A-weighted bands -> dB(A)
    A.LAeq(idx) = LA;
    if needBands, A.Lp(idx, :) = accLp;  A.LpA(idx, :) = accLpA;  A.LZ(idx) = nb_energy_sum(accLp, 2); end
    if detail
        A.Adiv(idx,:) = dAdiv; A.Aatm(idx,:) = dAatm; A.Agr(idx,:) = dAgr; A.Abar(idx,:) = dAbar;
        A.dom(idx) = domv; A.kind(idx) = dkind; A.dist(idx) = ddist; A.ground(idx) = o.ground;
    end
    if ~isempty(lim)
        C = compliance_arrays(accLp, accLpA, lim);
        A.code(idx) = C.code;  A.margin_overall(idx) = C.margin_overall;  A.worst_band(idx) = C.worst_band;
        A.worst_margin(idx) = C.worst_margin;  A.margin_bands(idx, :) = C.margin_bands;
    end
end
R.nSources = NS;  R.nObstacles = numel(obs);  R.closure_max_abs_dB = closure;  R.detail = detail;
R.enclosures = enc;  R.Lw_effective = reshape([SRC.Lw], 8, [])';
write_all(job, R, A);
end

% ------------------------------------------------------------------ points
function do_points(job)
base = make_base(job);
dem = read_dem(job);
obs = read_obstacles(job);
lim = read_limits(job);
NR = numel(job.receivers);  NS = numel(job.sources);
[SRC, enc] = prep_sources(job);
A.LAeq = nan(NR, 1);  A.LZ = nan(NR, 1);  A.Lp = nan(NR, 8);  A.LpA = nan(NR, 8);
A.Adiv = nan(NR, 8);  A.Aatm = nan(NR, 8);  A.Agr = nan(NR, 8);  A.Abar = nan(NR, 8);
A.dom = nan(NR, 1);   A.kind = nan(NR, 1);  A.ground = nan(NR, 1);  A.dist = nan(NR, 1);
reasons = cell(NR, 1);
total = NR;  wprog(job, 0, total, 'start');
for r = 1:NR
    Rc = job.receivers(r);
    ok = true;  best = -Inf;
    for s = 1:NS
        S = SRC(s);
        c = base;
        c.dem = dem;
        c.source = struct('x', S.x, 'y', S.y, 'h', S.h);
        c.Lw = S.Lw;
        c.Dc = S.Dc;
        c.receiver = struct('x', Rc.x, 'y', Rc.y, 'h', Rc.h);
        c.obstacles = obs;
        o = run_case_3d(c);
        if ~o.valid, ok = false; reasons{r} = o.reason; break; end
        q = o.out;
        if s == 1
            accLp = q.Lp;  accLpA = q.LpA_bands;
        else
            accLp  = nb_energy_sum([accLp; q.Lp], 1);
            accLpA = nb_energy_sum([accLpA; q.LpA_bands], 1);
        end
        if q.LpA_broadband > best
            best = q.LpA_broadband;
            dm = struct('s', s, 'Adiv', q.Adiv, 'Aatm', q.Aatm, 'Agr', q.Agr, 'Abar', q.Abar, ...
                'kind', o.geom.kind, 'd', q.d);
        end
    end
    if ok
        A.LAeq(r) = nb_energy_sum(accLpA);  A.Lp(r, :) = accLp;  A.LpA(r, :) = accLpA;  A.LZ(r) = nb_energy_sum(accLp);
        A.Adiv(r,:) = dm.Adiv;  A.Aatm(r,:) = dm.Aatm;  A.Agr(r,:) = dm.Agr;  A.Abar(r,:) = dm.Abar;
        A.dom(r) = dm.s;  A.dist(r) = dm.d;
        A.kind(r) = double(strcmp(dm.kind, 'blocked')) + 2*double(strcmp(dm.kind, 'clear_crest'));
        A.ground(r) = nb_dem_sample(dem, Rc.x, Rc.y);
    end
    wprog(job, r, total, sprintf('receiver %d of %d', r, NR));
end
if ~isempty(lim)
    C = compliance_arrays(A.Lp, A.LpA, lim);
    A.code = C.code;  A.margin_overall = C.margin_overall;  A.worst_band = C.worst_band;
    A.worst_margin = C.worst_margin;  A.margin_bands = C.margin_bands;
end
R.reasons = reasons;
R.enclosures = enc;
write_all(job, R, A);
end

% ------------------------------------------------------------------ material / atmosphere previews
function do_material(job)
% Transmission loss of one material as the core resolves it (mass law or measured), for the add-in's preview table.
m = nb_material('resolve', decode_mat(job.mat));
R.TL = m.TL;  R.TLeff = m.TLeff;  R.source = m.source;  R.confidence = m.confidence;
R.surface_mass = m.surface_mass;  R.warnings = m.warnings;  R.openness = m.openness;
R.fingerprint = nb_fingerprint();
wjson(job, R);
end

function do_atmosphere(job)
% Atmospheric absorption coefficient alpha (dB/km) per octave band, from the core.
a = job.atm;
b = nb_bands();
if strcmp(job.mode, 'iso1996')
    [~, alpha] = nb_aatm_1996(1000, a.T_C, a.RH);
else
    [~, alpha] = nb_aatm(1000, a.T_C, a.RH, a.p_kPa);
end
R.alpha_dB_per_km = alpha(:)';  R.f_nominal = b.f(:)';
R.fingerprint = nb_fingerprint();
wjson(job, R);
end
