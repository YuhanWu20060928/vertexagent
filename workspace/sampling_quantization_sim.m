%% sampling_quantization_sim.m
% 模拟信号采样与均匀量化（ADC 建模）仿真脚本
% 流程：生成模拟测试信号 -> 理想采样 -> 均匀量化 -> SQNR 评估 -> 频谱分析 -> 出图
% 环境：MATLAB R2024b
% 作者：VertexAgent

clc; close all; clear;

%% ---------- 1. 仿真参数 ----------
fs   = 8000;        % 采样率 [Hz]
T    = 0.512;       % 观测时长 [s]
f0   = 440;         % 基波频率 [Hz]（标准音 A4）
A    = 1.0;         % ADC 满量程幅度 [V]
nbit = 8;           % 量化位数 [bit]

assert(nbit >= 2 && nbit == fix(nbit), 'nbit 必须是不小于 2 的整数');
assert(fs > 2 * 3 * f0, '采样率不满足最高信号频率 3*f0 的 Nyquist 条件');

%% ---------- 2. 生成模拟信号（基波 + 三次谐波）----------
N  = round(fs * T);                 % 采样点数
assert(N >= 4, '采样点数 N 小于 4，请增大 T 或 fs');
t  = (0:N-1).' / fs;                % 时间轴（列向量）
xa = sin(2*pi*f0*t) + 0.35*sin(2*pi*3*f0*t);
pk = max(abs(xa));                  % 离散采样点上的信号峰值
assert(pk > 0, '测试信号幅度为零，无法归一化，请检查 f0 与 fs');
xa = A * xa / pk;                   % 归一化：峰值达到满量程

%% ---------- 3. 均匀量化（中升型，舍入量化）----------
Nlev  = 2^nbit;                                     % 量化级数
Delta = 2*A / Nlev;                                 % 量化步长 [V]
xq    = Delta * floor(xa / Delta + 0.5);            % 舍入到最近量化级
xq    = min(max(xq, -A + Delta/2), A - Delta/2);    % 限幅，防止过载
qerr  = xq - xa;                                    % 量化误差（改名 err->qerr，避免与环境中的同名变量/函数冲突）

%% ---------- 4. 性能指标：SQNR ----------
sigPow  = mean(xa.^2);                       % 信号平均功率
noiPow  = mean(qerr.^2);                     % 量化噪声平均功率
snrAct  = 10*log10(sigPow / noiPow);         % 实测信噪比 [dB]
snrFull = 6.02*nbit + 1.76;                  % 满幅正弦理论 SQNR [dB]
snrRef  = snrFull + 10*log10(sigPow / 0.5);  % 按本信号功率修正后的理论值 [dB]

fprintf('------------ ADC 量化仿真结果 ------------\n');
fprintf('采样率            : %g Hz\n', fs);
fprintf('采样点数          : %d\n', N);
fprintf('量化位数          : %d bit（%d 级）\n', nbit, Nlev);
fprintf('量化步长 Delta    : %.6f V\n', Delta);
fprintf('理论 SQNR(满幅)   : %.2f dB\n', snrFull);
fprintf('理论 SQNR(本信号) : %.2f dB\n', snrRef);
fprintf('实测 SQNR         : %.2f dB\n', snrAct);
fprintf('理论-实测偏差     : %.2f dB\n', abs(snrAct - snrRef));

%% ---------- 5. 频谱分析（验证基波峰值位置）----------
Nf   = floor(N/2);                  % 单边谱点数（用 floor 兼容奇数 N）
X    = fft(xq(:));
P    = abs(X(1:Nf+1)) / N;
P(2:end-1) = 2 * P(2:end-1);
f    = (0:Nf).' * fs / N;
[pkMag, idx] = max(P);
fPeak = f(idx);

%% ---------- 6. 自检（不通过直接报错）----------
assert(abs(max(abs(xa)) - A) < 1e-12, '信号峰值未归一化到满量程');
assert(max(abs(qerr)) <= Delta/2 + 1e-12, '量化误差超过 Delta/2');
assert(abs(snrAct - snrRef) < 1.0, '实测 SQNR 偏离理论值超过 1 dB');
assert(abs(fPeak - f0) <= fs/N, '频谱峰值频率与基波频率偏差超过一个频率分辨单元');
assert(pkMag > 0.7, '基波谱峰幅度异常偏低');
fprintf('PASS: 量化误差<=Delta/2, SQNR 偏差<1 dB, 谱峰 %.2f Hz 与 f0 一致\n', fPeak);

%% ---------- 7. 绘图并保存 ----------
fig = figure('Name','ADC 采样与量化仿真','Color','w','Position',[100 100 900 700]);
tl  = tiledlayout(fig, 3, 1, 'TileSpacing','compact');

ax1 = nexttile(tl);
M   = min(80, N);                           % 时域只画前 M 点，便于观察量化台阶（防止 M>N 越界）
stem(ax1, t(1:M)*1e3, xq(1:M), 'filled', 'MarkerSize', 3); hold(ax1,'on');
plot(ax1, t(1:M)*1e3, xa(1:M), 'r-', 'LineWidth', 1.2);
grid(ax1,'on'); xlabel(ax1,'时间 / ms'); ylabel(ax1,'幅度 / V');
legend(ax1, {'量化输出','模拟输入'}, 'Location','northeast');
title(ax1, sprintf('采样与量化（fs = %g Hz, %d bit, \\Delta = %.4f V）', fs, nbit, Delta));

ax2 = nexttile(tl);
plot(ax2, t*1e3, qerr/Delta, 'b-'); grid(ax2,'on');
xlim(ax2, [0 min(20, t(end)*1e3)]);          % 横轴上限随时长自适应，避免出现空图
xlabel(ax2,'时间 / ms'); ylabel(ax2,'误差 / \\Delta');
title(ax2, '量化误差（归一化到量化步长）');
yline(ax2,  0.5, 'r--'); yline(ax2, -0.5, 'r--');

ax3 = nexttile(tl);
plot(ax3, f, 20*log10(P + eps), 'LineWidth', 1.1); grid(ax3,'on');
xlim(ax3, [0 fs/2]); xlabel(ax3,'频率 / Hz'); ylabel(ax3,'幅度 / dB');
title(ax3, sprintf('量化输出频谱（基波谱峰 %.1f Hz）', fPeak));

exportgraphics(fig, 'adc_sim_result.png', 'Resolution', 150);
fprintf('图像已保存: adc_sim_result.png\n');
