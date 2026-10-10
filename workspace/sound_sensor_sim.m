%% sound_sensor_sim.m
% 声音传感器（驻极体 / MEMS 麦克风模块）采集链路与声音事件检测仿真
%
% 仿真链路：
%   声源声压 -> 麦克风换能(灵敏度) -> 前置放大 -> 直流偏置 -> 输出限幅
%            -> 12 bit ADC 量化 -> 去直流 -> 分段 RMS 包络 -> dB SPL
%            -> 阈值触发 + 去抖保持 -> 声音事件输出
%
% 运行环境：MATLAB R2024b，只用基础函数，不依赖任何工具箱
% 输出    ：命令窗口检测报告 + 工作区 4 张 png 图

clear; clc; close all;

%% ===================== 1. 仿真参数 =====================
fs   = 48000;                    % 采样率 (Hz)
Tsim = 1.0;                      % 仿真时长 (s)
t    = (0:1/fs:Tsim-1/fs).';     % 时间向量 (s)
N    = numel(t);
p_ref = 20e-6;                   % 参考声压 20 uPa
rng(7);                          % 固定随机数，结果可复现

sens_dBV = -38;                  % 麦克风灵敏度 (dBV/Pa)
sens_V   = 10^(sens_dBV/20);     % 电压灵敏度 (V/Pa)
gain     = 40;                   % 前置放大倍数
vdd      = 3.3;                  % 供电 / ADC 参考电压 (V)
v_bias   = vdd/2;                % 单电源直流偏置 (V)
nbit     = 12;                   % ADC 位数
lsb      = vdd/2^nbit;           % 量化步长 (V)
thr_spl  = 70;                   % 事件触发阈值 (dB SPL)
hold_ms  = 30;                   % 触发去抖保持时间 (ms)

%% ===================== 2. 声源合成 =====================
p_noise = 8e-4 * randn(N,1);                    % 环境本底噪声 (Pa)

f0  = 250;                                      % 谈话声基频 (Hz)
hum = zeros(N,1);                               % 预分配谐波叠加缓冲
for k = 1:4
    hum = hum + (1/k)*sin(2*pi*f0*k*t);         % 1~4 次谐波，幅度按 1/k
end
env_talk = 0.5*(1 + sin(2*pi*2*t));             % 2 Hz 说话节奏包络
p_talk   = 0.02 * env_talk .* hum;              % 谈话声 (Pa)

knock_pos  = round([0.28 0.62]*fs) + 1;         % 两次敲击事件起始样点
knock_len  = round(0.015*fs);                   % 敲击脉冲长度 15 ms
n_knock    = (0:knock_len-1).';
knock_wave = 0.9 * exp(-n_knock/(0.004*fs)) .* sin(2*pi*1200*n_knock/fs);
p_knock    = zeros(N,1);                        % 预分配敲击声缓冲
for ii = 1:numel(knock_pos)
    idx = knock_pos(ii) + n_knock;              % 定位写入，避免逐点循环
    p_knock(idx) = p_knock(idx) + knock_wave;
end

p_sound = p_noise + p_talk + p_knock;           % 到达麦克风的总声压 (Pa)

%% ===================== 3. 麦克风换能与模拟前端 =====================
v_mic = sens_V * p_sound;                       % 换能输出 (V)
v_amp = gain * v_mic;                           % 前置放大 (V)
v_afe = v_bias + v_amp;                         % 单电源直流偏置 (V)
v_afe = min(max(v_afe, 0), vdd);                % 输出限幅（削波）

%% ===================== 4. ADC 量化 =====================
code = round(v_afe/lsb);                        % 量化码值
code = min(max(code, 0), 2^nbit - 1);           % 限定有效码范围
adc  = code * lsb;                              % 量化后电压 (V)
%% ===================== 5. 数字域处理：RMS 包络与声压级 =====================
x     = adc - mean(adc);                        % 去直流
win   = 512;                                    % 帧长 512 点 ≈ 10.7 ms
hop   = win/2;                                  % 50% 重叠
w     = hann(win);                              % 汉宁窗
w_pow = sum(w.^2);                              % 窗能量归一化因子
nfrm  = floor((N - win)/hop) + 1;               % 帧数
env   = zeros(nfrm,1);                          % 预分配 RMS 包络 (V)
t_env = zeros(nfrm,1);                          % 预分配帧中心时刻 (s)
for m = 1:nfrm
    s0  = (m-1)*hop + 1;
    seg = x(s0:s0+win-1);
    env(m)   = sqrt(sum((seg.*w).^2)/w_pow);    % 无偏 RMS 电压
    t_env(m) = (s0 + win/2 - 1)/fs;
end

p_rms = env/(gain*sens_V);                      % 反推声压 RMS (Pa)
spl   = 20*log10(max(p_rms, eps)/p_ref);        % 声压级 (dB SPL)

%% ===================== 6. 阈值触发与事件提取 =====================
flag      = spl >= thr_spl;                     % 超阈值初判
hold_n    = max(1, round(hold_ms/1000*fs/hop)); % 保持帧数
flag_hold = flag;
last_on = -Inf;                                 % 最近一次超阈值帧号
for m = 1:nfrm
    if flag(m)
        last_on = m;                            % 刷新触发帧
    end
    if ~flag(m) && (m - last_on) <= hold_n
        flag_hold(m) = true;                    % 只在保持窗口内补位，不无限延长
    end
end

d      = diff([false; flag_hold; false]);       % 边沿检测
i_on   = find(d ==  1);
i_off  = find(d == -1) - 1;
nev    = min(numel(i_on), numel(i_off));
ev_str = t_env(i_on(1:nev));                    % 事件起始时刻 (s)
ev_end = t_env(i_off(1:nev));                   % 事件结束时刻 (s)
ev_dur = ev_end - ev_str;                       % 事件判定时长 (s)
ev_pk  = zeros(nev,1);                          % 预分配事件峰值
for k = 1:nev
    ev_pk(k) = max(spl(i_on(k):i_off(k)));
end

%% ===================== 7. 灵敏度标定自检 =====================
t_cal   = (0:1/fs:0.2-1/fs).';
p_cal   = sqrt(2)*p_ref*10^(94/20)*sin(2*pi*1000*t_cal);  % 94 dB SPL 标定声
v_cal   = min(max(gain*sens_V*p_cal + v_bias, 0), vdd);   % 通过模拟前端
c_cal   = min(max(round(v_cal/lsb), 0), 2^nbit-1) * lsb;  % ADC 量化后电压 (V)
spl_cal = 20*log10(rms(c_cal - mean(c_cal))/(gain*sens_V)/p_ref);

%% ===================== 8. 命令窗口报告 =====================
fprintf('========== 声音传感器仿真报告 ==========\n');
fprintf('采样率            : %d Hz\n', fs);
fprintf('仿真时长          : %.2f s (%d 点)\n', Tsim, N);
fprintf('麦克风灵敏度      : %.4f V/Pa (%.0f dBV/Pa)\n', sens_V, sens_dBV);
fprintf('前置放大 / 供电   : x%.1f / %.1f V\n', gain, vdd);
fprintf('ADC               : %d bit, LSB = %.3f mV\n', nbit, lsb*1e3);
fprintf('----------------------------------------\n');
fprintf('标定自检          : 输入 94.00 dB SPL -> 测得 %.2f dB SPL (误差 %+.2f dB)\n', spl_cal, spl_cal-94);
fprintf('本底噪声峰值      : %.1f dB SPL\n', 20*log10(max(abs(p_noise))/p_ref));
fprintf('谈话声峰值        : %.1f dB SPL\n', 20*log10(max(abs(p_talk))/p_ref));
fprintf('敲击声峰值        : %.1f dB SPL\n', 20*log10(max(abs(p_knock))/p_ref));
fprintf('触发阈值          : %.0f dB SPL\n', thr_spl);
fprintf('检出声音事件      : %d 个\n', nev);
for k = 1:nev
    fprintf('  事件 %d : 起始 %.3f s, 持续 %.1f ms, 峰值 %.1f dB SPL\n', ...
            k, ev_str(k), ev_dur(k)*1e3, ev_pk(k));
end
fprintf('========================================\n');
%% ===================== 9. 绘图并保存 png（无显示环境也可用） =====================
fig1 = figure('Visible','off','Color','w','Position',[80 80 900 640]);
subplot(3,1,1);
plot(t*1e3, p_sound*1e3, 'b'); grid on; xlim([0 100]);
xlabel('时间 (ms)'); ylabel('声压 (mPa)');
title('麦克风处总声压（本底噪声 + 谈话声）');
subplot(3,1,2);
plot(t, abs(p_sound)*1e3, 'Color',[0 0.45 0.74]); grid on;
xlabel('时间 (s)'); ylabel('|声压| (mPa)');
title('全时长声压包络：0.28 s 与 0.62 s 处两次敲击');
subplot(3,1,3);
sel = t >= 0.278 & t <= 0.292;
plot(t(sel)*1e3, p_sound(sel), 'r'); grid on;
xlabel('时间 (ms)'); ylabel('声压 (Pa)');
title('敲击事件局部放大（1.2 kHz 衰减振荡）');
exportgraphics(fig1, 'sound_sensor_waveform.png', 'Resolution', 120);

fig2 = figure('Visible','off','Color','w','Position',[80 80 900 420]);
sel2 = t >= 0.278 & t <= 0.280;
plot(t(sel2)*1e3, adc(sel2), 'k.-'); grid on;
xlabel('时间 (ms)'); ylabel('ADC 输出 (V)');
title(sprintf('%d bit ADC 量化输出（%d 级台阶，LSB = %.2f mV）', nbit, 2^nbit, lsb*1e3));
exportgraphics(fig2, 'sound_sensor_adc.png', 'Resolution', 120);

fig3 = figure('Visible','off','Color','w','Position',[80 80 900 460]);
hold on;
yb = [20 20 100 100];
for k = 1:nev
    patch([ev_str(k) ev_end(k) ev_end(k) ev_str(k)], yb, [1 0.9 0.9], ...
          'EdgeColor','none','FaceAlpha',0.8);
end
plot(t_env, spl, 'LineWidth', 1.4, 'Color', [0 0.45 0.74]);
yline(thr_spl, '--r', sprintf('触发阈值 %d dB SPL', thr_spl), 'LineWidth', 1.2);
hold off; grid on; set(gca,'Layer','top');
xlabel('时间 (s)'); ylabel('声压级 (dB SPL)');
xlim([0 Tsim]); ylim([20 100]);
title(sprintf('分段 RMS 包络声压级，检出 %d 个声音事件', nev));
exportgraphics(fig3, 'sound_sensor_spl.png', 'Resolution', 120);

fig4 = figure('Visible','off','Color','w','Position',[80 80 900 420]);
wn = hann(N);
X  = fft(x.*wn)/sum(wn);                        % 相干增益归一
Xa = abs(X(1:N/2+1))*2;                         % 单边幅值谱 (V)
Pa = Xa/(gain*sens_V);                          % 折算为声压幅值 (Pa)
f  = (0:N/2).'*fs/N;
L  = 20*log10(max(Pa, 1e-5*p_ref)/p_ref);       % 幅值谱电平 (dB SPL)
plot(f, L, 'Color', [0.1 0.1 0.1]); grid on;
xlim([0 6000]); ylim([-20 100]);
xlabel('频率 (Hz)'); ylabel('幅值谱 (dB SPL)');
title('数字输出幅值谱：250 Hz 谐波族 + 敲击宽带分量');
exportgraphics(fig4, 'sound_sensor_spectrum.png', 'Resolution', 120);

fprintf('图像已保存：sound_sensor_waveform.png / sound_sensor_adc.png\n');
fprintf('            sound_sensor_spl.png / sound_sensor_spectrum.png\n');
