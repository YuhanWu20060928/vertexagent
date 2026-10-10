%% sound_sensor.m
% 声音传感器（驻极体/MEMS 麦克风模块）数据采集与声级分析
%
% 处理流程：
%   原始采样 -> 去直流 -> 幅度归一化 -> 滑动包络 -> 帧 RMS
%            -> 声压级 dB SPL -> 阈值触发 -> 声音事件提取 -> 出图存档
%
% 数据来源：
%   1) 默认使用内置仿真信号（背景噪声 + 4 个声脉冲），无需硬件即可运行；
%   2) 若已用 Arduino/STM32 采集，把数据存成单列文本文件（每行一个采样值），
%      把 filePath 改为该文件路径即可，例如：
%          filePath = "C:\data\mic_01.txt";
%      Arduino 采集示例（需硬件）：
%          s = serialport("COM3", 115200);
%          configureTerminator(s, "LF");
%          data = readmatrix(s, "NumSamples", 8000);   % 8000 点 @8 kHz
%
% 运行环境：MATLAB R2024b，仅用基础函数，不依赖任何工具箱
% 输出    ：命令窗口分析报告 + sound_sensor_result.png

clear; close all; clc;

%% ===================== 1. 参数设置 =====================
filePath  = "";         % 数据文件路径；留空 = 使用内置仿真信号
fs        = 8e3;        % 采样率 (Hz)，须与采集端一致
thrRatio  = 0.30;       % 触发阈值（相对满量程 1.0）
pRef      = 20e-6;      % 参考声压 20 uPa
pMax      = 2.0;        % 满量程 1.0 对应的声压 (Pa)，按麦克风灵敏度换算
frameLen  = 1024;       % 帧长（样本）
hop       = 512;        % 帧移（样本），50% 重叠
smoothSec = 0.010;      % 包络平滑窗长 (s)
minEventT = 0.010;      % 最短有效事件时长 (s)，滤除毛刺
maxDur    = 30;         % 最长分析时长 (s)，防止内存溢出

%% ===================== 2. 获取采样数据 =====================
if strlength(filePath) == 0
    % ---- 2.1 内置仿真：本底噪声 + 4 个已知声脉冲（用于自检） ----
    isSim = true;
    n  = round(fs * 2.0);
    t  = (0:n-1).' / fs;
    rng(2024);                                   % 固定种子，结果可复现

    burstCenter = [0.30, 0.75, 1.20, 1.60];      % 声脉冲中心时刻 (s)
    burstDur    = [0.10, 0.06, 0.15, 0.08];      % 声脉冲时长 (s)
    burstAmp    = [0.60, 0.50, 0.80, 0.55];      % 声脉冲幅度
    fBurst      = 1000;                          % 声脉冲主频 (Hz)

    win    = abs(t - burstCenter) <= burstDur / 2;      % n x 4 逻辑矩阵（隐式扩展）
    ampVec = max(win .* burstAmp, [], 2);               % n x 1 逐点幅度包络
    x = 0.02 * randn(n,1) + ampVec .* sin(2*pi*fBurst*t) + 0.5 * ampVec .* randn(n,1);
    x = min(max(x, -1), 1);                             % 传感器输出限幅
    srcName = "内置仿真信号";
else
    % ---- 2.2 真实传感器数据：单列文本 / CSV ----
    isSim = false;
    assert(isfile(filePath), "找不到数据文件: " + filePath);
    raw = readmatrix(filePath);
    raw = raw(:,1);                                     % 只取第一列
    raw = raw(isfinite(raw));                           % 剔除 NaN / Inf
    nMax = round(maxDur * fs);
    if numel(raw) > nMax
        raw = raw(1:nMax);                              % 超长数据截断，防内存溢出
        warning("数据超过 %d s，仅分析前 %d s", maxDur, maxDur);
    end
    x  = double(raw(:));
    n  = numel(x);
    t  = (0:n-1).' / fs;
    mx = max(abs(x));
    if mx > 1
        x = x / mx;                                     % 原始 ADC 码值归一到 ±1
    end
    srcName = "文件数据 " + filePath;
end

assert(n >= 16, "有效采样点过少（%d 点），无法分析", n);

%% ===================== 3. 去直流与包络提取 =====================
x = x - mean(x);                                        % 去直流偏置

if n < frameLen                                         % 数据太短时自适应缩帧
    frameLen = n;
    hop      = max(1, floor(n/2));
end

env       = abs(x);                                     % 整流
envSmooth = movmean(env, max(1, round(smoothSec*fs)));  % 滑动平均包络

%% ===================== 4. 帧 RMS 与声压级（向量化分帧） =====================
nF  = floor((n - frameLen)/hop) + 1;                    % 帧数
idx = (0:frameLen-1).' + (0:nF-1)*hop;                  % frameLen x nF 索引矩阵
seg = x(idx + 1);                                       % 分帧矩阵

rmsF = sqrt(mean(seg.^2, 1)).';                         % 各帧 RMS（归一化）
rmsF = min(max(rmsF, 0), 1);
splF = 20*log10(max(rmsF * pMax, 1e-12) / pRef);        % 帧声压级 (dB SPL)
tF   = ((0:nF-1).' * hop + frameLen/2) / fs;            % 帧中心时刻 (s)

rmsAll  = sqrt(mean(x.^2));                             % 全程 RMS
splRms  = 20*log10(max(rmsAll * pMax, 1e-12) / pRef);   % 等效连续声级
peakAll = max(env);                                     % 峰值

%% ===================== 5. 阈值触发与声音事件提取 =====================
above = envSmooth > thrRatio;
d     = diff([false; above; false]);                    % 上升沿 +1，下降沿 -1
iOn   = find(d ==  1);
iOff  = find(d == -1) - 1;
nEv0  = min(numel(iOn), numel(iOff));
iOn   = iOn(1:nEv0);
iOff  = iOff(1:nEv0);

durEv = (iOff - iOn + 1) / fs;                          % 事件持续时长 (s)
keep  = durEv >= minEventT;                             % 滤除毛刺
iOn   = iOn(keep);
iOff  = iOff(keep);
durEv = durEv(keep);
nEv   = numel(iOn);

evT0   = zeros(nEv,1);                                  % 预分配事件起始时刻
evPeak = zeros(nEv,1);                                  % 预分配事件峰值
evSpl  = zeros(nEv,1);                                  % 预分配事件声压级
for k = 1:nEv
    evT0(k)   = t(iOn(k));
    segK      = x(iOn(k):iOff(k));
    evPeak(k) = max(abs(segK));
    evSpl(k)  = 20*log10(max(rms(segK) * pMax, 1e-12) / pRef);
end

%% ===================== 6. 自检 assert =====================
assert(isfinite(splRms) && splRms > 20 && splRms < 120, "总声压级异常: %.2f dB", splRms);
assert(nF == numel(splF) && nF == numel(tF),            "帧数与帧时间轴长度不一致");
assert(all(isfinite(splF)),                             "帧声压级含 NaN/Inf");
assert(peakAll > thrRatio,                              "信号峰值未超阈值，检测无意义");
assert(mean(envSmooth(1:round(0.05*fs))) < thrRatio,    "起始段本底噪声误触发");
if isSim
    assert(nEv == numel(burstCenter), ...
        "事件检测数 %d 与仿真脉冲数 %d 不一致", nEv, numel(burstCenter));
end
if nEv > 0
    assert(all(durEv >= minEventT), "存在短于最小有效时长的事件");
end

%% ===================== 7. 结果可视化 =====================
fig = figure("Name", "声音传感器分析", "Color", "w", "Position", [80 60 1040 800]);

subplot(3,1,1);
plot(t, x, "Color", [0.20 0.45 0.85], "LineWidth", 0.6);
grid on;
hold on;
yline( thrRatio, "--r", "触发阈值 +", "LineWidth", 1.0);
yline(-thrRatio, "--r", "触发阈值 -", "LineWidth", 1.0);
xlim([0, t(end)]);
xlabel("时间 (s)");
ylabel("归一化幅度");
title(sprintf("声音传感器原始波形（%s，fs = %g Hz）", srcName, fs));

subplot(3,1,2);
hold on;
grid on;
yTop = max(envSmooth) * 1.10 + 0.02;
for k = 1:nEv                                          % 高亮已检出的声音事件
    patch([t(iOn(k)) t(iOff(k)) t(iOff(k)) t(iOn(k))], ...
          [0 0 yTop yTop], [1 0.85 0.85], ...
          "EdgeColor", "none", "FaceAlpha", 0.55);
end
plot(t, envSmooth, "k", "LineWidth", 1.0);
yline(thrRatio, "--r", "阈值", "LineWidth", 1.0);
xlim([0, t(end)]);
ylim([0 max(yTop, thrRatio*1.3)]);
xlabel("时间 (s)");
ylabel("平滑包络");
title("包络检测与事件标记");

subplot(3,1,3);
plot(tF, splF, "Color", [0.85 0.33 0.10], "LineWidth", 1.0);
grid on;
hold on;
yline(splRms, "--k", sprintf("全程 %.1f dB", splRms), "LineWidth", 1.0);
xlim([0, t(end)]);
xlabel("时间 (s)");
ylabel("声压级 (dB SPL)");
title("帧声压级曲线");

outPng = "sound_sensor_result.png";
try
    exportgraphics(fig, outPng, "Resolution", 150);
catch
    saveas(fig, outPng);
end

%% ===================== 8. 命令窗口分析报告 =====================
fprintf("========== 声音传感器分析报告 ==========\n");
fprintf("数据来源    : %s\n", srcName);
fprintf("采样率      : %g Hz | 采样点 %d | 时长 %.3f s\n", fs, n, n/fs);
fprintf("分帧        : 帧长 %d / 帧移 %d -> %d 帧\n", frameLen, hop, nF);
fprintf("触发阈值    : %.3f (归一化)\n", thrRatio);
fprintf("---------------------------------------\n");
fprintf("峰值幅度    : %.4f\n", peakAll);
fprintf("全程 RMS    : %.4f -> %.1f dB SPL\n", rmsAll, splRms);
fprintf("帧声级范围  : %.1f ~ %.1f dB SPL\n", min(splF), max(splF));
fprintf("检出事件数  : %d 个\n", nEv);
if nEv > 0
    fprintf("  序号   起始(s)   时长(ms)   峰值    声级(dB)\n");
    for k = 1:nEv
        fprintf("  %2d   %7.3f   %8.1f   %6.3f   %8.1f\n", ...
            k, evT0(k), durEv(k)*1e3, evPeak(k), evSpl(k));
    end
end
fprintf("---------------------------------------\n");
fprintf("[PASS] 帧声压级全部有限，共 %d 帧\n", nF);
fprintf("[PASS] 全程声级 %.1f dB 落在合理区间 (20, 120)\n", splRms);
fprintf("[PASS] 本底噪声段未误触发\n");
if isSim
    fprintf("[PASS] 事件数 %d == 仿真脉冲数 %d\n", nEv, numel(burstCenter));
end
fprintf("[PASS] 结果图已保存: %s\n", outPng);
fprintf("=======================================\n");
