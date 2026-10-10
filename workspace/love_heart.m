%% love_heart.m ---------------------------------------------------------
%  浪漫表白动图：心跳脉动的心形 + 星光闪烁 + 渐显告白文字，导出 GIF
%  运行环境：MATLAB R2024b，仅用基础功能，无需任何工具箱
%  输出    ：love_heart.gif（动图）、love_heart_final.png（终帧静图）
% ----------------------------------------------------------------------
clear; clc; close all;

%% ---------------- 1. 参数 ----------------
outGif = 'love_heart.gif';          % 动图文件名
outPng = 'love_heart_final.png';    % 终帧静图
R      = 480;                       % 输出帧边长（像素）
nStep  = 96;                        % 总帧数
dT     = 0.05;                      % 帧间隔（秒）

LINE1  = 'I  L O V E  Y O U';       % 告白文字（主）
LINE2  = '爱你，从第一眼开始';       % 告白文字（副）
FONT   = 'Microsoft YaHei';

%% ---------------- 2. 心形参数方程 ----------------
t  = linspace(0, 2*pi, 1600).';                          % 参数
hx = 16*sin(t).^3 / 17;                                   % x 归一化
hy = (13*cos(t) - 5*cos(2*t) - 2*cos(3*t) - cos(4*t)) / 17;
hy = hy - (max(hy) + min(hy))/2;                          % 垂直居中
N  = numel(t);

%% ---------------- 3. 星点（背景星光） ----------------
rng(2024);                                                % 固定随机种子
nS     = 150;
starX  = 2.8*rand(nS,1) - 1.4;
starY  = 2.8*rand(nS,1) - 1.6;
starPh = 2*pi*rand(nS,1);
starSz = 6 + 26*rand(nS,1);
starSp = 0.8 + 2.2*rand(nS,1);

%% ---------------- 4. 画布与背景渐变 ----------------
fig = figure('Visible','off', 'Color',[0.02 0.01 0.06], ...
             'Position',[80 80 R R], 'Renderer','opengl', ...
             'PaperPositionMode','auto', 'InvertHardcopy','off');

ax = axes('Parent',fig, 'Position',[0 0 1 1]);
hold(ax,'on');
axis(ax,'equal');
set(ax, 'Color','none', 'XLim',[-1.4 1.4], 'YLim',[-1.6 1.2], ...
    'XTick',[], 'YTick',[], 'Box','off');

% 背景：深紫黑 + 中心微红的径向渐变
[gx, gy] = meshgrid(linspace(-1.4,1.4,300), linspace(-1.6,1.2,300));
rr  = sqrt(gx.^2 + gy.^2);
bg  = zeros(300,300,3);
bg(:,:,1) = 0.05 + 0.13*exp(-rr.^2/0.9);
bg(:,:,2) = 0.01 + 0.02*exp(-rr.^2/1.2);
bg(:,:,3) = 0.09 + 0.20*exp(-rr.^2/1.6);
image(ax, [-1.4 1.4], [-1.6 1.2], bg);                    % 铺背景
set(ax,'YDir','normal');

% 星光散点（背景层）
hStar = scatter(ax, starX, starY, starSz, [1 0.8 0.9], 'filled', ...
                'MarkerFaceColor','flat', 'MarkerEdgeColor','none');

% 心形光晕（由外到内三层）
hGlow1 = plot(ax, hx, hy, '-', 'Color',[0.34 0.03 0.09], 'LineWidth',30);
hGlow2 = plot(ax, hx, hy, '-', 'Color',[0.62 0.06 0.18], 'LineWidth',14);
hGlow3 = plot(ax, hx, hy, '-', 'Color',[0.90 0.14 0.32], 'LineWidth',6);

% 心形填充 + 主轮廓
hFill = patch(ax, 'XData',hx, 'YData',hy, 'FaceColor',[0.88 0.07 0.22], ...
              'EdgeColor','none', 'FaceAlpha',0);
hLine = plot(ax, hx, hy, '-', 'Color',[1.00 0.42 0.60], 'LineWidth',3.2);

% 文字区柔光（椭圆光斑，初始全透明，随文字渐显亮起）
th  = linspace(0, 2*pi, 200).';
hHalo = patch(ax, 0.95*cos(th), -1.17 + 0.30*sin(th), [1.00 0.55 0.72], ...
              'EdgeColor','none', 'FaceAlpha',0);

% 告白文字（心形下方，带描边保证任何背景都清晰）
hT1 = text(ax, 0, -1.02, LINE1, 'Color',[0 0 0], 'FontName',FONT, ...
           'FontSize',26, 'FontWeight','bold', ...
           'HorizontalAlignment','center', 'VerticalAlignment','middle');
hT2 = text(ax, 0, -1.32, LINE2, 'Color',[0 0 0], 'FontName',FONT, ...
           'FontSize',16, 'FontWeight','bold', ...
           'HorizontalAlignment','center', 'VerticalAlignment','middle');

%% ---------------- 5. 逐帧动画 ----------------
TXT_ON = [0.62 0.88];        % 文字渐显的起止进度
tmpPng = [tempname '.png'];

for k = 1:nStep
    ph = (k-1)/(nStep-1);                        % 总进度 0→1

    % ---- 心跳脉动（生长完成后开始） ----
    if ph > 0.38
        pp   = mod(ph - 0.38, 0.42)/0.42;        % 单次心跳周期
        beat = 0.085*exp(-((pp-0.10)/0.050)^2) + ...
               0.055*exp(-((pp-0.30)/0.058)^2); % 双峰“咚-咚”
        sc   = 1 + beat;
    else
        sc   = 1;
    end

    % ---- 轮廓自顶部缺口起笔描出 ----
    gRow  = min(1, ph/0.38);                     % 生长进度
    nShow = max(4, round(gRow*N));

    set(hGlow1, 'XData', hx(1:nShow)*sc*1.000, 'YData', hy(1:nShow)*sc*1.000);
    set(hGlow2, 'XData', hx(1:nShow)*sc*1.030, 'YData', hy(1:nShow)*sc*1.030);
    set(hGlow3, 'XData', hx(1:nShow)*sc*1.055, 'YData', hy(1:nShow)*sc*1.055);
    set(hLine,  'XData', hx(1:nShow)*sc,       'YData', hy(1:nShow)*sc);

    % ---- 填充随脉动呼吸 ----
    fa = max(0, min(0.92, 0.22 + 0.70*gRow + 0.55*max(0, sc-1)));
    set(hFill, 'XData', hx*sc, 'YData', hy*sc, 'FaceAlpha', fa);

    % ---- 星光闪烁（亮度、尺寸、微漂移） ----
    br = 0.18 + 0.82*(0.5 + 0.5*sin(2*pi*starSp*3*ph + starPh));
    set(hStar, ...
        'XData',    starX + 0.05*sin(2*pi*starSp*2*ph + starPh), ...
        'YData',    starY + 0.05*cos(2*pi*starSp*2*ph + starPh), ...
        'SizeData', starSz.*(0.55 + 0.75*br), ...
        'CData',    [br, 0.74*br, 0.96*br]);

    % ---- 文字渐显并轻微上浮 ----
    aT = max(0, min(1, (ph - TXT_ON(1))/(TXT_ON(2) - TXT_ON(1))));
    aT = aT^0.8;
    cT = [0.05 0.02 0.08]*(1-aT) + [1.00 0.94 0.97]*aT;   % 背景色→亮粉白
    set(hT1, 'Color', cT, 'Position', [0, -1.02 + 0.05*(1-aT), 0]);
    set(hT2, 'Color', cT*0.92, 'Position', [0, -1.32 + 0.04*(1-aT), 0]);

    % ---- 文字区柔光：随文字渐显而亮起，衬托告白 ----
    set(hHalo, 'FaceAlpha', 0.55*aT);

    drawnow limitrate;

    % ---- 抓帧并写入 GIF ----
    frame = grabFrame(fig, tmpPng, R);
    [gi, cmap] = rgb2ind(frame, 256);            % 量化到 256 色
    if k == 1
        imwrite(gi, cmap, outGif, 'gif', 'LoopCount',Inf, ...
                'DelayTime',dT, 'WriteMode','overwrite');
    else
        imwrite(gi, cmap, outGif, 'gif', ...
                'DelayTime',dT, 'WriteMode','append');
    end
    lastFrame = frame;                            %#ok<NASGU>
    fprintf('渲染帧 %2d / %2d\r', k, nStep);
end

imwrite(lastFrame, outPng);                       % 保存终帧静图
if exist(tmpPng,'file'), delete(tmpPng); end

fprintf('\n完成：%s（%d 帧）\n', outGif, nStep);
fprintf('静图：%s\n', outPng);

%% ---------------- 6. 局部函数：稳健抓帧 ----------------
function img = grabFrame(fig, tmpFile, R)
% 优先用 getframe 抓帧（速度快），失败则回退 print
    try
        fr  = getframe(fig);
        img = fr.cdata;
        if isempty(img) || mean(img(:)) < 1e-6
            error('getframe 结果无效，改用 print');
        end
    catch
        print(fig, tmpFile, '-dpng', '-r96');
        img = imread(tmpFile);
    end
    [h, w, ~] = size(img);
    if h ~= R || w ~= R                              % 统一到 R×R
        img = img(round(linspace(1,h,R)), round(linspace(1,w,R)), :);
    end
end
