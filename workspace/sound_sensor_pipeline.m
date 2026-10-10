function res = sound_sensor_pipeline()
%SOUND_SENSOR_PIPELINE 声音传感器采集链路仿真（R2024b，仅用基础函数，不依赖工具箱）
%
%   仿真链路：
%     声源声压 -> 自由场 1/r 传播 -> 麦克风换能(灵敏度) -> 前置放大
%     -> 直流偏置 -> 二阶带通(双二阶级联, 带宽 300~3400 Hz) -> 12 bit ADC 量化
%     -> 去偏置反算声压 -> dB SPL 估计 -> 阈值报警 -> assert 自检
%
%   用法：
%     res = sound_sensor_pipeline;     % 返回全部中间量，并保存 png
%
%   输出 res 字段：
%     t       时间轴 (s)            p_src   声源声压 (Pa)
%     p_mic   麦克风处声压 (Pa)     v_afe   模拟前端输出 (V)
%     v_adc   ADC 量化输出 (V)      p_est   反算声压 (Pa)
%     spl_src 声源声压级 (dB SPL)   spl_mic 麦克风处真值 (dB SPL)
%     spl_est 量化后估计值 (dB SPL) alarm   报警标志 (logical)

%% ===================== 1. 仿真参数 =====================
fs     = 16000;                     % 采样率 (Hz)
Tsim   = 0.25;                      % 仿真时长 (s)
N      = round(fs*Tsim);
t      = (0:N-1).'/fs;

f_tone = 1000;  A_tone  = 1.4142;   % 主音频率/幅值 (Hz, Pa)
f_harm = 2500;  A_harm  = 0.30;     % 二次谐波 (Hz, Pa)
A_noise = 0.02;                     % 本底噪声标准差 (Pa)

r_ref  = 1.0;                       % 参考距离 (m)
r_mic  = 2.0;                       % 声源到麦克风距离 (m)

sens_dBV = -40;                     % 麦克风灵敏度 (dBV/Pa)
sens     = 10^(sens_dBV/20);        % 电压灵敏度 (V/Pa) = 10 mV/Pa
gain   = 100;                       % 前置放大倍数 (40 dB)
vdd    = 3.3;                       % 供电 / ADC 参考电压 (V)
v_bias = vdd/2;                     % 单电源直流偏置 (V)
nbit   = 12;                        % ADC 位数
lsb    = vdd/2^nbit;                % 量化步长 (V)

f_low  = 300;                       % 带通下限 -3 dB 频率 (Hz)
f_high = 3400;                      % 带通上限 -3 dB 频率 (Hz)
p_ref  = 20e-6;                     % 参考声压 (Pa)
thr_spl = 85;                       % 报警阈值 (dB SPL)

rng(0);                             % 固定随机种子，结果可复现

%% ===================== 2. 声源与自由场传播 =====================
p_src = A_tone*sin(2*pi*f_tone*t) + A_harm*sin(2*pi*f_harm*t) + A_noise*randn(N,1);
p_mic = p_src*(r_ref/r_mic);        % 球面波 1/r 衰减

spl_src = 20*log10(local_rms(p_src)/p_ref);
spl_mic = 20*log10(local_rms(p_mic)/p_ref);

%% ===================== 3. 麦克风换能与模拟前端 =====================
v_afe = v_bias + gain*sens*p_mic;                   % 偏置 + 放大
if any(v_afe < 0 | v_afe > vdd)                     % 越界则削波
    warning("ADC input clipped to supply rails");
    v_afe = min(max(v_afe,0),vdd);
end

%% ===================== 4. 带通滤波（两级二阶，-3 dB 带宽 = f_high-f_low） =====================
f0 = sqrt(f_low*f_high);                            % 几何中心频率 (Hz)
Q1 = (f0/(f_high-f_low))*2.4142;                    % 两级级联后 -3 dB 带宽落回 [f_low,f_high]
[b,a] = local_biquad_bp(f0,Q1,fs);
x_ac  = v_afe - v_bias;                             % 去掉直流偏置再滤波
y     = filter(b,a,filter(b,a,x_ac));               % 两级级联

%% ===================== 5. 12 bit ADC 量化 =====================
code  = round((y + v_bias)/lsb);                    % 量化码值
code  = min(max(code,0),2^nbit-1);                  % 限定有效码
v_adc = code*lsb;                                   % 量化后电压 (V)
q_err = v_adc - (y + v_bias);                       % 量化误差 (V)

%% ===================== 6. 反算声压与声压级 =====================
i_ss    = round(N/2)+1:N;                           % 稳态段，跳过滤波器暂态
p_est   = (v_adc - v_bias)/(gain*sens);             % 反算声压 (Pa)
p_ideal = (y - mean(y))/(gain*sens);                % 未量化反算，用于对比
spl_est   = 20*log10(local_rms(p_est(i_ss))/p_ref);
spl_ideal = 20*log10(local_rms(p_ideal(i_ss))/p_ref);
alarm     = spl_est > thr_spl;

%% ===================== 7. 自检 assert =====================
tc    = (0:round(0.2*fs)-1).'/fs;
g_in  = local_amp_ss(filter(b,a,filter(b,a,sin(2*pi*f_tone*tc)))); % 通带增益
g_lo  = local_amp_ss(filter(b,a,filter(b,a,sin(2*pi*50*tc))));     % 50 Hz 抑制
g_hi  = local_amp_ss(filter(b,a,filter(b,a,sin(2*pi*6000*tc))));   % 6 kHz 抑制
assert(abs(g_in-1) < 0.05,              "passband gain at 1 kHz = %.4f", g_in);
assert(g_lo < 0.06,                     "50 Hz rejection failed, gain = %.4f", g_lo);
assert(g_hi < 0.06,                     "6 kHz rejection failed, gain = %.4f", g_hi);
assert(local_rms(q_err) < lsb,          "quantization error exceeds 1 LSB");
assert(abs(spl_est-spl_ideal) < 0.5,    "quantization degrades level estimate too much");
assert(abs(spl_mic-spl_est) < 3,        "reconstructed SPL deviates from true value");
assert(all(abs(v_adc - v_bias) <= vdd/2), "ADC output out of range");
assert(spl_est-26 < thr_spl,            "quiet scene (x0.05) should not alarm");

%% ===================== 8. 命令窗口报告 =====================
fprintf("========== sound sensor pipeline ==========\n");
fprintf("fs / frames / duration : %d Hz / %d / %.2f s\n", fs, N, Tsim);
fprintf("microphone sens.       : %.1f mV/Pa (%.0f dBV/Pa)\n", sens*1e3, sens_dBV);
fprintf("preamp gain / supply   : x%.0f (%.0f dB) / %.1f V\n", gain, 20*log10(gain), vdd);
fprintf("ADC                    : %d bit, LSB = %.3f mV\n", nbit, lsb*1e3);
fprintf("band-pass              : %.0f - %.0f Hz, Q_stage = %.3f\n", f_low, f_high, Q1);
fprintf("-------------------------------------------\n");
fprintf("source SPL @ %.0f m      : %.2f dB SPL\n", r_ref, spl_src);
fprintf("SPL at mic  @ %.0f m     : %.2f dB SPL (true)\n", r_mic, spl_mic);
fprintf("estimated SPL (ADC)    : %.2f dB SPL, deviation %+.2f dB\n", spl_est, spl_est-spl_mic);
fprintf("quantization noise rms : %.4f mV (%.4f LSB)\n", local_rms(q_err)*1e3, local_rms(q_err)/lsb);
fprintf("alarm threshold        : %d dB SPL -> alarm = %d\n", thr_spl, alarm);
fprintf("PASS: all 8 self-checks passed\n");
fprintf("===========================================\n");

%% ===================== 9. 绘图并保存 png =====================
fig = figure("Visible","off","Color","w","Position",[80 80 900 780]);

ax1 = subplot(3,1,1);
plot(ax1, t*1e3, p_src, "b"); grid(ax1,"on"); xlim(ax1,[0 8]);
xlabel(ax1,"时间 (ms)"); ylabel(ax1,"声压 (Pa)");
title(ax1, sprintf("声源声压 %.1f dB SPL @ %.0f m，传到麦克风处 %.1f dB SPL", ...
      spl_src, r_ref, spl_mic));

ax2 = subplot(3,1,2);
plot(ax2, t*1e3, v_afe, "Color",[0.85 0.33 0.10]); hold(ax2,"on");
plot(ax2, t*1e3, v_adc, ".", "Color",[0 0.45 0.74], "MarkerSize",3); hold(ax2,"off");
grid(ax2,"on"); xlim(ax2,[0 4]);
xlabel(ax2,"时间 (ms)"); ylabel(ax2,"电压 (V)");
title(ax2, sprintf("模拟前端输出与 %d bit ADC 量化输出（LSB = %.2f mV，偏置 %.2f V）", ...
      nbit, lsb*1e3, v_bias));
legend(ax2, {"模拟 v_{afe}","量化 v_{adc}"}, "Location","northeast");

ax3 = subplot(3,1,3);
seg  = p_est(i_ss) - mean(p_est(i_ss));
Lseg = numel(seg);
fk   = (0:Lseg-1).'*fs/Lseg;
Pk   = abs(fft(seg))*2/Lseg;                        % 单边幅值谱 (Pa)
nh   = floor(Lseg/2);
plot(ax3, fk(1:nh), 20*log10(max(Pk(1:nh),1e-12)/p_ref), "k");
grid(ax3,"on"); xlim(ax3,[0 6000]); ylim(ax3,[-20 100]);
xlabel(ax3,"频率 (Hz)"); ylabel(ax3,"幅值谱 (dB SPL)");
title(ax3, sprintf("重建声压幅值谱：1 kHz 分量 %.1f dB SPL，2.5 kHz 按带通特性衰减，带外噪声被抑制", ...
      spl_est));

exportgraphics(fig, "sound_sensor_pipeline.png", "Resolution", 120);
fprintf("figure saved: sound_sensor_pipeline.png\n");

%% ===================== 10. 返回结果 =====================
res = struct("t",t, "p_src",p_src, "p_mic",p_mic, "v_afe",v_afe, ...
             "v_adc",v_adc, "p_est",p_est, "spl_src",spl_src, ...
             "spl_mic",spl_mic, "spl_est",spl_est, "alarm",alarm);
end

%% ===================== 局部函数 =====================
function [b,a] = local_biquad_bp(f0,Q,fs)
%LOCAL_BIQUAD_BP RBJ 二阶带通（峰值增益 0 dB），归一化后 a(1) = 1
w0    = 2*pi*f0/fs;
alpha = sin(w0)/(2*Q);
b0 =  alpha;  b1 = 0;  b2 = -alpha;
a0 = 1+alpha; a1 = -2*cos(w0); a2 = 1-alpha;
b = [b0 b1 b2]/a0;
a = [1 a1/a0 a2/a0];
end

function y = local_rms(x)
%LOCAL_RMS 有效值
y = sqrt(mean(x(:).^2));
end

function A = local_amp_ss(y)
%LOCAL_AMP_SS 取后一半样本的峰值，作为稳态正弦幅值估计
n = numel(y);
A = max(abs(y(round(n/2):end)));
end
