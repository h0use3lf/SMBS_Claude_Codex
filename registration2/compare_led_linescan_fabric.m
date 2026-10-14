function results=compare_led_linescan_fabric(rootDir,forceReload,options)
% Compare registered LED and line-scan white-reference relative signals.
% No registration or source writes. VNIR and SWIR are separate regions.
% options: outputDir, representativeSample (index or run label), showFigures,
% optionalBandDeviation, optionalCellRMSE, optionalColorSpectra, optionalPCA.
% Example: compare_led_linescan_fabric(dataRoot,false,struct('showFigures',false))
% Cells are correlated spatial regions, not independent physical specimens.
% MATLAB R2020b+; no additional toolbox required.
if nargin<1 || isempty(rootDir),rootDir='C:\Users\박원교\OneDrive\바탕 화면\led_10_03\정합2';end
if nargin<2 || isempty(forceReload),forceReload=false;end

cfg.gridN=6;                 % 셀 격자 (6 -> 시료당 36셀)
cfg.minPixels=50;            % 셀당 최소 공통 유효 화소 수
cfg.ranges=[400 1000;1000 1700]; % 라인스캔 분석 파장 범위 [VNIR; SWIR] (nm)
cfg.ledGroups={1:26,27:32};  % 각 격자에서 비교할 LED 번호
cfg.ledFWHMnm=0;             % 0: LED 중심파장에서 선형보간, >0: 해당 FWHM의 가우시안 대역 평균
cfg.nPC=10;                  % PCA-LDA에 쓰는 주성분 수(상한)
cfg.kNN=3;
cfg.kFold=5;
cfg.seed=1;
cfg.showFigures=true;        % false면 화면에 띄우지 않고 PNG만 저장
cfg.resolution=200;          % PNG 해상도(dpi)

cfg.representativeSample=1;
cfg.optionalBandDeviation=false;cfg.optionalCellRMSE=false;
cfg.optionalColorSpectra=false;cfg.optionalPCA=false;
cfg.outputDir=fullfile(fileparts(mfilename('fullpath')),'comparison_results');
if nargin<3 || isempty(options),options=struct;end
assert(isstruct(options) && isscalar(options),'options must be a scalar struct');
fn=fieldnames(options);
for ii=1:numel(fn)
    assert(isfield(cfg,fn{ii}),'Unknown option: %s',fn{ii});
    cfg.(fn{ii})=options.(fn{ii});
end
assert(cfg.ledFWHMnm==0,'This study uses linear interpolation at LED center wavelengths.');
assert(cfg.gridN>=1 && cfg.gridN==fix(cfg.gridN) && cfg.minPixels>=1,'Invalid grid settings');
assert(cfg.kFold==5 && cfg.kNN==3,'Use 5-fold and 3-NN for this study');
outDir=cfg.outputDir;
% Prevent outputs anywhere inside the source data tree.
sourceCanonical=char(java.io.File(rootDir).getCanonicalPath());
outCanonical=char(java.io.File(outDir).getCanonicalPath());
assert(~strcmpi(sourceCanonical,outCanonical) && ~startsWith(lower(outCanonical),[lower(sourceCanonical) filesep]), ...
    'outputDir must be outside the original data directory.');
if ~isfolder(outDir),mkdir(outDir);end
runs=findRuns(rootDir);
assert(~isempty(runs),'정합이 완료된 run 폴더를 찾지 못했습니다: %s',rootDir);
fprintf('분석 대상 시료 %d개: %s\n',numel(runs),strjoin({runs.label},', '));

% ---------- 1) 셀 평균 스펙트럼 추출 (캐시 사용) ----------
cachePath=fullfile(outDir,'cell_spectra_cache.mat');
key=struct('version',3,'implementation',fileread([mfilename('fullpath') '.m']), ...
    'cfg',cfg,'inputs',{inputFingerprints(runs)});
D=[];
if ~forceReload && isfile(cachePath)
    C=load(cachePath);
    if isfield(C,'key') && isfield(C,'D') && isequal(C.key,key),D=C.D;fprintf('캐시 사용: %s\n',cachePath);end
end
if isempty(D)
    D=extractCellSpectra(runs,cfg);
    save(cachePath,'D','key');
end
for p=1:2
    D.hsiAtLed{p}=resampleToLED(D.hsi{p},D.wave{p},D.waveLED{p},cfg.ledFWHMnm);
    if any(D.waveLED{p}<min(D.wave{p}) | D.waveLED{p}>max(D.wave{p}))
        warning('LED wavelengths outside the %s HSI range; no extrapolation. Affected comparison is unavailable.',runs(1).pairNames{p});
    end
end
v=any(D.valid,2);
fprintf('유효 셀 %d / %d\n',nnz(D.valid),numel(D.valid));

fabricNames=displayFabric(D.fabrics);nF=numel(D.fabrics);nCo=numel(D.colors);
fabricColors=[0 .447 .698;.835 .369 0;0 .62 .451;.8 .475 .655;.337 .706 .914;.902 .624 0];
fabricColors=fabricColors(mod(0:nF-1,size(fabricColors,1))+1,:);
dyeMarkers={'o','s','^','d','v','p'};dyeMarkers=dyeMarkers(mod(0:nCo-1,6)+1);
sampleLabels=cell(numel(runs),1);
for s=1:numel(runs)
    sampleLabels{s}=sprintf('%s-%s',fabricNames{runs(s).fabricIdx},D.colors{runs(s).colorIdx});
end
style=struct('font',pickFont(),'visible',cfg.showFigures,'res',cfg.resolution,'out',outDir);
hsiColor=[.25 .25 .25];ledColor=[.835 .369 0];
rangeNames={'VNIR (separate registered region)','SWIR (separate registered region)'};
shortRange={'VNIR','SWIR'};

% ---------- 2) 스펙트럼 일치도 지표 ----------
LEDall=[D.led{1} D.led{2}];HSIall=[D.hsiAtLed{1} D.hsiAtLed{2}];waveLEDall=[D.waveLED{1};D.waveLED{2}];
pairsA=D.led;pairsB=D.hsiAtLed;
for r=1:2,cellMetric(r)=agreementMetrics(pairsA{r},pairsB{r});end %#ok<AGROW>
metricNames={'RMSE','Bias','SAMdeg','PearsonR'};
nS=numel(runs);sampleMetric=nan(nS,2,4);rows={};
for s=1:nS
    for r=1:2
        m=D.valid(:,r) & D.sample==s;
        sampleMetric(s,r,:)=[mean(cellMetric(r).rmse(m),'omitnan') mean(cellMetric(r).bias(m),'omitnan') ...
            mean(cellMetric(r).sam(m),'omitnan') mean(cellMetric(r).r(m),'omitnan')];
        rows(end+1,:)={sampleLabels{s},runs(s).name,shortRange{r},nnz(m),sampleMetric(s,r,1), ...
            sampleMetric(s,r,2),sampleMetric(s,r,3),sampleMetric(s,r,4)}; %#ok<AGROW>
    end
end
sampleTable=cell2table(rows,'VariableNames',[{'Sample','Run','Range','Cells'},metricNames]);
writetable(sampleTable,fullfile(outDir,'sample_agreement.csv'),'Encoding','UTF-8');

d=LEDall-HSIall;nB=numel(waveLEDall);bandR=nan(nB,1);bandSlope=bandR;
for k=1:nB
    good=isfinite(HSIall(:,k)) & isfinite(LEDall(:,k));
    if nnz(good)<2,continue;end
    c=corrcoef(HSIall(good,k),LEDall(good,k));bandR(k)=c(1,2);
    if std(HSIall(good,k))>0,q=polyfit(HSIall(good,k),LEDall(good,k),1);bandSlope(k)=q(1);end
end
bandTable=table((1:nB)',waveLEDall,mean(d,1,'omitnan')',std(d,0,1,'omitnan')',sqrt(mean(d.^2,1,'omitnan'))',bandR,bandSlope, ...
    'VariableNames',{'LEDNumber','WavelengthNm','MeanLEDminusScan','StdLEDminusScan','RMSE','PearsonR','Slope'});
writetable(bandTable,fullfile(outDir,'band_agreement.csv'));

registrationFigure(runs,cfg,style);
% ---------- Fig 1: 시료별 스펙트럼 비교 ----------
f=newFig('Fig2 시료별 스펙트럼',[40 60 1500 900],style);
tl=tiledlayout(f,nF,nCo,'Padding','compact','TileSpacing','compact');
top=max([D.hsi{1}(:);D.hsi{2}(:);LEDall(:)],[],'omitnan');if isempty(top)||~isfinite(top)||top<=0,top=1;end
for s=1:nS
    ax=nexttile(tl,(runs(s).fabricIdx-1)*nCo+runs(s).colorIdx);hold(ax,'on');
    for p=1:2
        m=D.valid(:,p) & D.sample==s;
        if ~any(m),text(ax,.03,.9-.08*p,sprintf('%s: no valid cells',shortRange{p}),'Units','normalized');end
        mu=mean(D.hsi{p}(m,:),1,'omitnan');sd=std(D.hsi{p}(m,:),0,1);w=D.wave{p}';
        fill(ax,[w fliplr(w)],[mu-sd fliplr(mu+sd)],hsiColor,'FaceAlpha',.2,'EdgeColor','none','HandleVisibility','off');
        h1=plot(ax,w,mu,'-','Color',hsiColor,'LineWidth',1.3);
    end
    h2=errorbar(ax,waveLEDall,mean(LEDall(D.sample==s,:),1,'omitnan'),std(LEDall(D.sample==s,:),0,1,'omitnan'),'o','Color',ledColor, ...
        'MarkerFaceColor',ledColor,'MarkerSize',4,'CapSize',3,'LineStyle','none');
    xline(ax,1000,':','Color',[.5 .5 .5],'HandleVisibility','off');
    xlim(ax,[400 1700]);ylim(ax,[0 top*1.05]);grid(ax,'on');box(ax,'on');
    title(ax,sprintf('%s | VNIR n=%d, SWIR n=%d',sampleLabels{s},nnz(D.valid(:,1)&D.sample==s),nnz(D.valid(:,2)&D.sample==s)));
    if s==1,legend(ax,[h1 h2],{'라인스캔 (평균 ± 셀 간 SD)','LED (평균 ± 셀 간 SD)'},'Location','southeast');end
end
xlabel(tl,'파장 (nm)','FontName',style.font);ylabel(tl,'white 기준 상대 신호','FontName',style.font);
title(tl,'시료별 평균 ± 셀 간 SD | VNIR·SWIR은 별도 영역','FontName',style.font,'FontWeight','bold');
saveFig(f,'Fig02_sample_spectra',style);

% ---------- Fig 2: 산점도 + Bland-Altman ----------
f=newFig('Fig3 일치도 산점도',[60 60 1200 950],style);
tl=tiledlayout(f,2,2,'Padding','compact','TileSpacing','compact');
for p=1:2
    vp=D.valid(:,p) & all(isfinite(D.hsiAtLed{p}),2);X=D.hsiAtLed{p}(vp,:);Y=D.led{p}(vp,:);cls=repmat(D.fabricIdx(vp),1,size(X,2));
    if isempty(X),for ti=[p 2+p],ax=nexttile(tl,ti);text(ax,.1,.5,'No valid cells');axis(ax,'off');end;continue;end
    ax=nexttile(tl,p);hold(ax,'on');h=gobjects(nF,1);
    for c=1:nF
        h(c)=scatter(ax,X(cls==c),Y(cls==c),8,fabricColors(c,:),'filled','MarkerFaceAlpha',.25);
    end
    lim=[min(0,min([X(:);Y(:)])) max(eps,max([X(:);Y(:)]))*1.05];plot(ax,lim,lim,'k--','HandleVisibility','off');
    q=[NaN NaN];if std(X(:))>0,q=polyfit(X(:),Y(:),1);plot(ax,lim,polyval(q,lim),'-','Color',[.3 .3 .3],'HandleVisibility','off');end
    c2=corrcoef(X(:),Y(:));e=Y(:)-X(:);
    text(ax,.04,.96,sprintf('n = %d\nR^2 = %.3f\nRMSE = %.4f\nBias = %+.4f\ny = %.3fx %+.3f', ...
        numel(e),c2(1,2)^2,sqrt(mean(e.^2)),mean(e),q(1),q(2)),'Units','normalized', ...
        'VerticalAlignment','top','BackgroundColor','w','EdgeColor',[.7 .7 .7]);
    axis(ax,'square');xlim(ax,lim);ylim(ax,lim);grid(ax,'on');box(ax,'on');
    xlabel(ax,'라인스캔 (LED 파장 위치)');ylabel(ax,'LED');title(ax,rangeNames{p});
    if p==1,legend(ax,h,fabricNames,'Location','southeast');end
    ax=nexttile(tl,2+p);hold(ax,'on');
    for c=1:nF
        scatter(ax,(X(cls==c)+Y(cls==c))/2,Y(cls==c)-X(cls==c),8,fabricColors(c,:),'filled','MarkerFaceAlpha',.25);
    end
    yline(ax,mean(e),'k-',sprintf('평균 %+.4f',mean(e)),'LabelHorizontalAlignment','left');
    yline(ax,mean(e)+1.96*std(e),'k--',sprintf('+1.96SD %+.4f',mean(e)+1.96*std(e)),'LabelHorizontalAlignment','left');
    yline(ax,mean(e)-1.96*std(e),'k--',sprintf('-1.96SD %+.4f',mean(e)-1.96*std(e)), ...
        'LabelHorizontalAlignment','left','LabelVerticalAlignment','bottom');
    grid(ax,'on');box(ax,'on');xlabel(ax,'(LED + 라인스캔) / 2');ylabel(ax,'LED - 라인스캔');
    title(ax,['Bland-Altman | ' shortRange{p}]);
end
title(tl,'셀·밴드 단위 기술적 일치도 | HSI를 LED 중심 파장에 선형보간','FontName',style.font,'FontWeight','bold');
saveFig(f,'Fig03_agreement_scatter',style);

if cfg.optionalBandDeviation
% ---------- Fig 3: LED 밴드별 편차 ----------
f=newFig('Fig3 밴드별 편차',[80 60 1400 800],style);
tl=tiledlayout(f,2,1,'Padding','compact','TileSpacing','compact');
ax=nexttile(tl);hold(ax,'on');off=linspace(-.22,.22,nF);
for c=1:nF
    m=D.fabricIdx==c;dd=LEDall(m,:)-HSIall(m,:);
    errorbar(ax,(1:nB)+off(c),mean(dd,1,'omitnan'),std(dd,0,1,'omitnan'),'o','Color',fabricColors(c,:), ...
        'MarkerFaceColor',fabricColors(c,:),'MarkerSize',4,'CapSize',3,'LineStyle','none');
end
yline(ax,0,'k-','HandleVisibility','off');xline(ax,numel(D.waveLED{1})+.5,':','Color',[.5 .5 .5],'HandleVisibility','off');
bandAxis(ax,waveLEDall);ylabel(ax,'LED - 라인스캔 (평균 ± SD)');legend(ax,fabricNames,'Location','best');
title(ax,'LED 밴드별 편차 (원단별, 셀 간 분포)');
ax=nexttile(tl);
yyaxis(ax,'left');bar(ax,1:nB,bandR,'FaceColor',[.6 .7 .85],'EdgeColor','none');ylabel(ax,'셀 간 Pearson r');
ylim(ax,[min(0,min(bandR)) 1]);
yyaxis(ax,'right');plot(ax,1:nB,bandTable.RMSE,'-o','Color',ledColor,'MarkerFaceColor',ledColor,'MarkerSize',4);
ylabel(ax,'RMSE');ax.YAxis(1).Color=[.2 .3 .5];ax.YAxis(2).Color=ledColor;
xline(ax,numel(D.waveLED{1})+.5,':','Color',[.5 .5 .5]);bandAxis(ax,waveLEDall);
title(ax,'LED 밴드별 상관계수(막대)와 RMSE(선) — 전체 시료·셀');
saveFig(f,'Optional_band_agreement',style);
end

if cfg.optionalCellRMSE
% ---------- Fig 5: 셀 단위 RMSE 분포 ----------
f=newFig('Fig5 셀 RMSE 분포',[120 60 1300 700],style);
tl=tiledlayout(f,2,1,'Padding','compact','TileSpacing','compact');
for p=1:2
    ax=nexttile(tl);hold(ax,'on');
    for s=1:nS
        m=D.valid(:,p) & D.sample==s;
        boxchart(ax,s*ones(nnz(m),1),cellMetric(p).rmse(m),'BoxFaceColor',fabricColors(runs(s).fabricIdx,:), ...
            'MarkerColor',fabricColors(runs(s).fabricIdx,:),'MarkerStyle','.');
    end
    xticks(ax,1:nS);xticklabels(ax,sampleLabels);xlim(ax,[.4 nS+.6]);grid(ax,'on');box(ax,'on');
    ylabel(ax,'셀별 RMSE');title(ax,rangeNames{p});
end
title(tl,sprintf('시료 내 공간적 일치도 분포 (%dx%d 셀)',cfg.gridN,cfg.gridN),'FontName',style.font,'FontWeight','bold');
saveFig(f,'Optional_cell_rmse',style);
end

if cfg.optionalColorSpectra
% ---------- Fig 6: 염색 색상별 원단 평균 스펙트럼 ----------
f=newFig('Fig6 원단별 스펙트럼',[140 60 1500 520],style);
tl=tiledlayout(f,1,nCo,'Padding','compact','TileSpacing','compact');
for co=1:nCo
    ax=nexttile(tl);hold(ax,'on');h=gobjects(0);lab={};
    for c=1:nF
        m=v & D.fabricIdx==c & D.colorIdx==co;if ~any(m),continue;end
        for p=1:2,h1=plot(ax,D.wave{p},mean(D.hsi{p}(m,:),1,'omitnan'),'-','Color',fabricColors(c,:),'LineWidth',1.3);end
        plot(ax,waveLEDall,mean(LEDall(m,:),1,'omitnan'),'o','Color',fabricColors(c,:),'MarkerFaceColor','w','MarkerSize',5,'LineWidth',1.1);
        h(end+1)=h1;lab{end+1}=fabricNames{c}; %#ok<AGROW>
    end
    xline(ax,1000,':','Color',[.5 .5 .5]);xlim(ax,[400 1700]);ylim(ax,[0 top*1.05]);grid(ax,'on');box(ax,'on');
    title(ax,['염색 색상 ' D.colors{co}]);
    if co==1,legend(ax,h,lab,'Location','southeast');end
end
xlabel(tl,'파장 (nm)','FontName',style.font);ylabel(tl,'white 기준 상대 신호','FontName',style.font);
title(tl,'같은 염색 색상에서의 원단별 스펙트럼 (실선: 라인스캔, ○: LED)','FontName',style.font,'FontWeight','bold');
saveFig(f,'Optional_color_spectra',style);
end

% ---------- 3) 분류용 특징 구성 ----------
featNames={'LED','라인스캔@LED파장','라인스캔 전체밴드'};
F=cell(2,3);
F(1,:)={D.led{1},D.hsiAtLed{1},D.hsi{1}};
F(2,:)={D.led{2},D.hsiAtLed{2},D.hsi{2}};
% No concatenation: the two regions are not mutually registered.
% Keep region-specific rows; classification filters each range separately.
y=D.fabricIdx;dye=D.colorIdx;

if cfg.optionalPCA
% ---------- Fig 7: PCA 점수 ----------
f=newFig('Fig7 PCA',[60 40 1400 1000],style);
tl=tiledlayout(f,2,3,'Padding','compact','TileSpacing','compact');
for r=1:2
    for k=1:3
        ax=nexttile(tl);hold(ax,'on');vp=D.valid(:,r);X=F{r,k}(vp,:);X=X-mean(X,1);
        if size(X,1)<2 || size(X,2)<2,text(ax,.1,.5,'Insufficient data');continue;end
        [U,S,~]=svd(X,'econ');sc=U(:,1:2)*S(1:2,1:2);ev=diag(S).^2;ev=100*ev/sum(ev);
        for c=1:nF
            for co=1:nCo
                m=y(vp)==c & dye(vp)==co;
                scatter(ax,sc(m,1),sc(m,2),22,fabricColors(c,:),dyeMarkers{co},'filled','MarkerFaceAlpha',.6);
            end
        end
        grid(ax,'on');box(ax,'on');xlabel(ax,sprintf('PC1 (%.1f%%)',ev(1)));ylabel(ax,sprintf('PC2 (%.1f%%)',ev(2)));
        title(ax,sprintf('%s | %s (%d밴드)',shortRange{r},featNames{k},size(X,2)));
    end
end
ax=nexttile(tl,1);h=gobjects(0);lab={};
for c=1:nF,h(end+1)=scatter(ax,nan,nan,30,fabricColors(c,:),'o','filled');lab{end+1}=fabricNames{c};end %#ok<AGROW>
for co=1:nCo,h(end+1)=scatter(ax,nan,nan,30,[.4 .4 .4],dyeMarkers{co});lab{end+1}=['염색 ' D.colors{co}];end %#ok<AGROW>
lg=legend(ax,h,lab,'Orientation','horizontal');lg.Layout.Tile='south';
title(tl,'PCA 점수 분포: 색=원단, 마커=염색 색상','FontName',style.font,'FontWeight','bold');
saveFig(f,'Optional_pca',style);
end

% Classification is independent for each registered region.
[accTable,conf,acc,statusTable]=classificationAnalysis(D,F,cfg,shortRange,featNames,outDir);
classificationFigure(acc,conf,fabricNames,shortRange,style,statusTable);
results=struct('cfg',cfg,'runs',runs,'data',D,'sampleLabels',{sampleLabels}, ...
    'sampleAgreement',sampleTable,'bandAgreement',bandTable,'accuracy',accTable, ...
    'confusion',{conf},'validationStatus',statusTable,'outputDir',outDir);
save(fullfile(outDir,'comparison_results.mat'),'results');
fprintf('Cells are spatial regions, not independent specimens. Random cell 5-fold can share the same specimen between train and test.\n');
fprintf('Outputs: %s\n',outDir);
if nargout==0,clear results;end
end
% ======================================================================
function runs=findRuns(rootDir)
% dataset_selection.mat 과 nan_background 큐브가 모두 있는 run 폴더만 사용한다.
d=dir(fullfile(rootDir,'*_run_*'));d=d([d.isdir]);[~,order]=sort({d.name});d=d(order);
runs=struct('name',{},'dir',{},'pairNames',{},'fabric',{},'color',{},'label',{},'fabricIdx',{},'colorIdx',{});
for i=1:numel(d)
    folder=fullfile(rootDir,d(i).name);manifest=fullfile(folder,'dataset_selection.mat');
    if ~isfile(manifest),warning('dataset_selection.mat 없음, 건너뜀: %s',d(i).name);continue;end
    S=load(manifest,'dataset');names=cellstr(S.dataset.pairNames);ok=true;
    for p=1:2
        base=fullfile(folder,'ct_or_preprocessed_registration',names{p},'calibrated_cubes','nan_background');
        ok=ok && isfile(fullfile(base,'LED_cube_32_corrected.mat')) && isfile(fullfile(base,'linescan_cube_corrected.mat')) ...
            && isfile(fullfile(base,'fabric_mask.mat'));
    end
    if ~ok,warning('마스크된 큐브가 없어 건너뜀(4단계 미완료): %s',d(i).name);continue;end
    tok=strsplit(names{1},'_');assert(numel(tok)>=3,'시료 이름 형식이 <원단>_<색상>_VNIR 이 아님: %s',names{1});
    r=struct('name',d(i).name,'dir',folder,'pairNames',{names},'fabric',lower(tok{1}),'color',upper(tok{2}), ...
        'label',[lower(tok{1}) '_' upper(tok{2})],'fabricIdx',0,'colorIdx',0);
    same=find(strcmp({runs.label},r.label));
    if ~isempty(same)
        warning('같은 시료의 run이 여러 개여서 최신 것만 사용: %s',r.label);runs(same)=r;
    else
        runs(end+1)=r; %#ok<AGROW>
    end
end
fabrics=unique({runs.fabric},'stable');colors=unique({runs.color});
for i=1:numel(runs)
    runs(i).fabricIdx=find(strcmp(fabrics,runs(i).fabric));runs(i).colorIdx=find(strcmp(colors,runs(i).color));
end
end

function D=extractCellSpectra(runs,cfg)
% 셀 번호: 행 우선, 좌상단=1 (analyze_ct_or_grid와 동일). 셀 안에서 선택된 모든
% LED/라인스캔 밴드가 유한한 화소만 평균한다.
g=cfg.gridN;nC=g^2;nR=numel(runs);N=nR*nC;
D.sample=repelem((1:nR)',nC);D.cell=repmat((1:nC)',nR,1);
D.fabricIdx=repelem([runs.fabricIdx]',nC);D.colorIdx=repelem([runs.colorIdx]',nC);
D.fabrics=unique({runs.fabric},'stable');D.colors=unique({runs.color});
D.count=zeros(N,2);D.led=cell(1,2);D.hsi=cell(1,2);D.wave=cell(1,2);D.waveLED=cell(1,2);
for s=1:nR
    map=readtable(fullfile(runs(s).dir,'LED_wavelength_mapping.csv'));
    assert(isequal(map.LEDNumber,(1:32)'),'LED 파장 매핑 오류: %s',runs(s).name);
    for p=1:2
        fprintf('[%d/%d] %s 읽는 중...\n',(s-1)*2+p,nR*2,runs(s).pairNames{p});
        base=fullfile(runs(s).dir,'ct_or_preprocessed_registration',runs(s).pairNames{p},'calibrated_cubes','nan_background');
        L=load(fullfile(base,'LED_cube_32_corrected.mat'),'ledCube','channelIDs');
        S=load(fullfile(base,'linescan_cube_corrected.mat'),'scanCube','wavelengthNm');
        M=load(fullfile(base,'fabric_mask.mat'),'fabricMask');mask=M.fabricMask;
        assert(isequal(L.channelIDs(:),(0:31)'),'LED 채널 순서가 예상과 다름');
        assert(isequal(size(mask),size(L.ledCube,[1 2])) && isequal(size(mask),size(S.scanCube,[1 2])),'큐브/마스크 크기 불일치');
        nums=cfg.ledGroups{p};w=double(S.wavelengthNm(:));
        idx=find(w>=cfg.ranges(p,1) & w<=cfg.ranges(p,2));[ws,order]=sort(w(idx));idx=idx(order);
        assert(numel(ws)>=2 && all(diff(ws)>0),'HSI range needs at least two distinct wavelengths: %s',runs(s).pairNames{p});
        waveLED=map.WavelengthNm(nums);
        if s==1
            D.wave{p}=ws;D.waveLED{p}=waveLED;D.led{p}=nan(N,numel(nums));D.hsi{p}=nan(N,numel(idx));
        else
            assert(numel(ws)==numel(D.wave{p}) && max(abs(ws-D.wave{p}))<.01,'시료 간 라인스캔 파장이 다름');
            assert(isequal(waveLED,D.waveLED{p}),'시료 간 LED 파장 매핑이 다름');
        end
        pix=find(mask);[my,mx]=ind2sub(size(mask),pix);
        if isempty(pix),warning('Empty fabric mask: %s',runs(s).pairNames{p});continue;end
        xEdges=round(linspace(min(mx),max(mx)+1,g+1));yEdges=round(linspace(min(my),max(my)+1,g+1));
        A=reshape(L.ledCube,[],32);A=double(A(pix,nums));
        B=reshape(S.scanCube,[],size(S.scanCube,3));B=double(B(pix,idx));
        ok=all(isfinite(A),2) & all(isfinite(B),2);A=A(ok,:);B=B(ok,:);
        id=(discretize(my(ok),yEdges)-1)*g+discretize(mx(ok),xEdges);
        n=accumarray(id,1,[nC 1]);W=sparse(id,(1:numel(id))',1,nC,numel(id));
        ledMean=(W*A)./n;scanMean=(W*B)./n;few=n<cfg.minPixels;ledMean(few,:)=NaN;scanMean(few,:)=NaN;
        rowsOut=(s-1)*nC+(1:nC);D.led{p}(rowsOut,:)=ledMean;D.hsi{p}(rowsOut,:)=scanMean;D.count(rowsOut,p)=n;
        clear L S A B
    end
end
D.valid=D.count>=cfg.minPixels;
end

function Y=resampleToLED(X,wave,waveLED,fwhm)
% 행=스펙트럼. 평균은 선형이므로 셀 평균 스펙트럼에 적용해도 화소별 적용과 같다.
if fwhm<=0
    Y=interp1(wave,X.',waveLED(:),'linear',NaN).';
else
    W=exp(-4*log(2)*((wave(:)'-waveLED(:))/fwhm).^2);W=W./sum(W,2);Y=X*W.';
end
end

function m=agreementMetrics(A,B)
% 행별(셀별) LED(A) vs 라인스캔(B) 지표.
d=A-B;m.rmse=sqrt(mean(d.^2,2));m.bias=mean(d,2);
denom=vecnorm(A,2,2).*vecnorm(B,2,2);
cosine=sum(A.*B,2)./denom;
m.sam=acosd(max(-1,min(1,cosine)));
m.sam(denom==0 | ~isfinite(cosine))=NaN;
Ac=A-mean(A,2);Bc=B-mean(B,2);m.r=sum(Ac.*Bc,2)./(vecnorm(Ac,2,2).*vecnorm(Bc,2,2));
end

function pred=classifyFabric(Xtr,ytr,Xte,K,method,cfg)
% 학습 데이터 통계로 표준화 후 1) PCA-LDA(공통 공분산, 동일 사전확률) 2) k-NN.
mu=mean(Xtr,1);sd=std(Xtr,0,1);sd(sd<1e-12)=1;Xtr=(Xtr-mu)./sd;Xte=(Xte-mu)./sd;
if method==1
    [~,S,V]=svd(Xtr,'econ');sv=diag(S);
    k=max(1,min([cfg.nPC,nnz(sv>sv(1)*1e-8),size(Xtr,1)-K]));
    T=Xtr*V(:,1:k);Tte=Xte*V(:,1:k);Mu=zeros(K,k);Sw=zeros(k);present=false(K,1);
    for c=1:K
        m=ytr==c;if ~any(m),continue;end
        present(c)=true;Mu(c,:)=mean(T(m,:),1);R=T(m,:)-Mu(c,:);Sw=Sw+R'*R;
    end
    Sw=Sw/max(1,size(T,1)-nnz(present));Sw=Sw+max(1e-8,1e-6*trace(Sw)/k)*eye(k);
    G=Sw\Mu';score=Tte*G-.5*sum(Mu'.*G,1);score(:,~present)=-Inf;
    [~,pred]=max(score,[],2);
else
    d2=sum(Xte.^2,2)+sum(Xtr.^2,2)'-2*Xte*Xtr';[~,order]=sort(d2,2);
    k=min(cfg.kNN,size(Xtr,1));near=ytr(order(:,1:k));near=reshape(near,[],k);
    votes=zeros(size(Xte,1),K);
    for c=1:K,votes(:,c)=sum(near==c,2);end
    votes(sub2ind(size(votes),(1:size(Xte,1))',near(:,1)))=votes(sub2ind(size(votes),(1:size(Xte,1))',near(:,1)))+.5; % 동률이면 최근접
    [~,pred]=max(votes,[],2);
end
end

function names=displayFabric(keys)
known={'ct','면';'cotton','면';'ny','나일론';'nylon','나일론';'poly','폴리에스터';'pe','폴리에스터';'polyester','폴리에스터'};
names=keys;
for i=1:numel(keys)
    j=find(strcmp(known(:,1),keys{i}),1);if ~isempty(j),names{i}=known{j,2};end
end
end

function font=pickFont()
font=get(groot,'defaultAxesFontName');fonts=listfonts;
for c={'Malgun Gothic','맑은 고딕','NanumGothic','AppleGothic'}
    if any(strcmpi(fonts,c{1})),font=c{1};return;end
end
end

function f=newFig(name,pos,style)
vis='on';if ~style.visible,vis='off';end
f=figure('Name',name,'Color','w','Position',pos,'Visible',vis, ...
    'DefaultAxesFontName',style.font,'DefaultTextFontName',style.font,'DefaultLegendFontName',style.font);
end

function saveFig(f,name,style)
drawnow;exportgraphics(f,fullfile(style.out,[name '.png']),'Resolution',style.res);
end

function bandAxis(ax,wave)
xticks(ax,1:numel(wave));xticklabels(ax,compose('%d',round(wave)));xtickangle(ax,60);
xlim(ax,[.3 numel(wave)+.7]);grid(ax,'on');box(ax,'on');xlabel(ax,'LED 중심 파장 (nm)');
end

function c=pickText(useWhite)
if useWhite,c=[1 1 1];else,c=[0 0 0];end
end

function stamps=inputFingerprints(runs)
% SHA-256 of every extraction input, including manifests and wavelength maps.
% Content hashes prevent stale reuse even if size/timestamp are unchanged.
stamps=cell(0,2);
for s=1:numel(runs)
    paths={fullfile(runs(s).dir,'dataset_selection.mat'),fullfile(runs(s).dir,'LED_wavelength_mapping.csv')};
    for p=1:2
        base=fullfile(runs(s).dir,'ct_or_preprocessed_registration',runs(s).pairNames{p},'calibrated_cubes','nan_background');
        for name={'LED_cube_32_corrected.mat','linescan_cube_corrected.mat','fabric_mask.mat'}
            paths{end+1}=fullfile(base,name{1}); %#ok<AGROW>
        end
    end
    for j=1:numel(paths)
        md=java.security.MessageDigest.getInstance('SHA-256');
        fid=fopen(paths{j},'rb');assert(fid>=0,'Cannot read %s',paths{j});
        cleanup=onCleanup(@()fclose(fid));
        while true
            chunk=fread(fid,1048576,'*uint8');if isempty(chunk),break;end
            md.update(typecast(chunk,'int8'));
        end
        digest=typecast(md.digest(),'uint8');
        stamps(end+1,:)={paths{j},lower(reshape(dec2hex(digest,2).',1,[]))}; %#ok<AGROW>
        clear cleanup
    end
end
end

function registrationFigure(runs,cfg,style)
s=cfg.representativeSample;
if ischar(s)||isstring(s)
    s=find(strcmp({runs.label},char(s))|strcmp({runs.name},char(s)),1);
end
assert(~isempty(s)&&isscalar(s)&&s==fix(s)&&s>=1&&s<=numel(runs),'Invalid representativeSample');
f=newFig('Fig1 Existing registration',[40 50 1250 600],style);
tl=tiledlayout(f,1,2,'Padding','compact');
for p=1:2
    ax=nexttile(tl);base=fullfile(runs(s).dir,'ct_or_preprocessed_registration',runs(s).pairNames{p});
    path=fullfile(base,'overlay.png');
    if isfile(path),image(ax,imread(path));axis(ax,'image');axis(ax,'off');
    else,text(ax,.05,.5,'Stored overlay.png unavailable; no new registration performed');axis(ax,'off');end
    title(ax,runs(s).pairNames{p},'Interpreter','none');
    % Preserve existing per-tape boundary error and shape QC without claiming
    % that these quantify whole-fabric registration accuracy.
    path=fullfile(base,'tape_shape_metrics.csv');
    if isfile(path)
        copyfile(path,fullfile(style.out,sprintf('registration_%s_existing_tape_QC.csv',runs(s).pairNames{p})));
        qc=readtable(path);
        if ismember('BoundaryRmsPx',qc.Properties.VariableNames)
            vals=qc.BoundaryRmsPx;
            title(ax,sprintf('%s | Tape RMS %.3f–%.3f px',runs(s).pairNames{p},min(vals),max(vals)),'Interpreter','none');
        end
    end
end
% Keep only panel titles: image axes can otherwise overlap a layout title.
saveFig(f,'Fig01_registration',style);
end

function [T,conf,acc,statusT]=classificationAnalysis(D,F,cfg,ranges,features,outDir)
K=numel(D.fabrics);acc=nan(2,3,2,2);conf=cell(2,3,2,2);
rows=cell(0,9);status=cell(0,4);cmRows=cell(0,8);foldRows=cell(0,9);
validation={'Leave-one-color-out','Random-cell-5-fold'};methods={'PCA-LDA','3-NN'};
for r=1:2
    good=D.valid(:,r);
    for k=1:3,good=good & all(isfinite(F{r,k}),2);end
    y=D.fabricIdx(good);dye=D.colorIdx(good);smp=D.sample(good);
    rng(cfg.seed);fd=zeros(size(y));
    for s=unique(smp)'
        ix=find(smp==s);fd(ix(randperm(numel(ix))))=mod(0:numel(ix)-1,cfg.kFold)+1;
    end
    folds={dye,fd};
    for cv=1:2
        valid=true;reason='OK';ids=unique(folds{cv});
        if K<2 || numel(unique(y))<K
            valid=false;reason='Insufficient fabric classes';
        elseif cv==1 && numel(unique(dye))<2
            valid=false;reason='At least two colors are required';
        elseif cv==2 && numel(ids)<cfg.kFold
            valid=false;reason='Insufficient cells for five nonempty folds';
        end
        if valid
            for fo=ids'
                tr=folds{cv}~=fo;
                counts=accumarray(y(tr),1,[K 1]);
                if any(counts<2) || nnz(tr)<=K
                    valid=false;reason='Each training fold requires at least two cells per fabric and residual degrees of freedom';break;
                end
            end
        end
        status(end+1,:)={ranges{r},validation{cv},valid,reason}; %#ok<AGROW>
        if ~valid,warning('%s / %s: %s',ranges{r},validation{cv},reason);end
        for k=1:3
            X=F{r,k}(good,:);
            for q=1:2
                C=zeros(K);pred=nan(size(y));
                if valid
                    for fo=ids'
                        te=folds{cv}==fo;
                        pred(te)=classifyFabric(X(~te,:),y(~te),X(te,:),K,q,cfg);
                        foldRows(end+1,:)={ranges{r},features{k},validation{cv},methods{q},fo,nnz(~te),nnz(te),numel(unique(smp(te))),100*mean(pred(te)==y(te))}; %#ok<AGROW>
                    end
                    acc(r,k,cv,q)=100*mean(pred==y);C=accumarray([y pred],1,[K K]);
                else
                    C(:)=NaN;
                end
                conf{r,k,cv,q}=C;
                rows(end+1,:)={ranges{r},features{k},size(X,2),validation{cv},methods{q},acc(r,k,cv,q),numel(y),numel(unique(smp)),reason}; %#ok<AGROW>
                for i=1:K
                    for j=1:K
                        cmRows(end+1,:)={ranges{r},features{k},validation{cv},methods{q},D.fabrics{i},D.fabrics{j},C(i,j),100*C(i,j)/max(sum(C(i,:)),1)}; %#ok<AGROW>
                    end
                end
            end
        end
    end
end
T=cell2table(rows,'VariableNames',{'Range','FeatureSet','NumBands','Validation','Classifier','AccuracyPct','Cells','PhysicalSamples','Status'});
statusT=cell2table(status,'VariableNames',{'Range','Validation','Available','Reason'});
writetable(T,fullfile(outDir,'classification_accuracy.csv'),'Encoding','UTF-8');
writetable(statusT,fullfile(outDir,'validation_status.csv'),'Encoding','UTF-8');
writetable(cell2table(cmRows,'VariableNames',{'Range','FeatureSet','Validation','Classifier','Actual','Predicted','Count','RowPct'}),fullfile(outDir,'classification_confusion.csv'),'Encoding','UTF-8');
writetable(cell2table(foldRows,'VariableNames',{'Range','FeatureSet','Validation','Classifier','Fold','TrainCells','TestCells','TestPhysicalSamples','AccuracyPct'}),fullfile(outDir,'classification_folds.csv'),'Encoding','UTF-8');
end

function classificationFigure(acc,conf,names,ranges,style,statusT)
f=newFig('Fig4 Fabric classification',[70 40 1300 850],style);
tl=tiledlayout(f,2,2,'Padding','compact','TileSpacing','compact');
for r=1:2
    ax=nexttile(tl,r);A=reshape(acc(r,:,1,:),3,2);
    st=statusT(strcmp(statusT.Range,ranges{r}) & strcmp(statusT.Validation,'Leave-one-color-out'),:);
    if all(isnan(A(:)))
        text(ax,.05,.5,{'Color exclusion unavailable',char(st.Reason{1})},'Interpreter','none');axis(ax,'off');
    else
        b=bar(ax,A,'grouped');
        b(1).FaceColor=[.3 .5 .7];b(2).FaceColor=[.85 .45 .15];
        xticks(ax,1:3);xticklabels(ax,{'LED','Scan @ LED','Scan full bands'});ylim(ax,[0 125]);
        for q=1:2
            text(ax,b(q).XEndPoints,b(q).YEndPoints,compose('%.1f%%',b(q).YData), ...
                'HorizontalAlignment','center','VerticalAlignment','bottom','FontSize',10);
        end
        legend(ax,b,{'PCA-LDA','3-NN'},'Location','northwest','Orientation','horizontal');
        ylabel(ax,'Cell accuracy (%)');grid(ax,'on');
    end
    title(ax,[ranges{r} ' | PCA-LDA vs 3-NN | color exclusion']);
    ax=nexttile(tl,2+r);C=conf{r,1,1,1};
    if all(isnan(C(:)))
        text(ax,.05,.5,'Confusion matrix unavailable');axis(ax,'off');
    else
        P=100*C./max(sum(C,2),1);imagesc(ax,P,[0 100]);colormap(ax,flipud(gray));axis(ax,'square');
        for i=1:numel(names)
            for j=1:numel(names)
                text(ax,j,i,sprintf('%.1f%%\n(%d)',P(i,j),C(i,j)),'HorizontalAlignment','center','Color',pickText(P(i,j)>55),'FontSize',12);
            end
        end
        xticks(ax,1:numel(names));yticks(ax,1:numel(names));xticklabels(ax,names);yticklabels(ax,names);xlabel(ax,'Predicted');ylabel(ax,'Actual');
    end
    title(ax,[ranges{r} ' | LED / PCA-LDA confusion']);
end
title(tl,{'Within-system fabric classification | leave one color out', ...
    'Representative matrices: LED in each region, selected before results; cells are not independent specimens'});
saveFig(f,'Fig04_classification',style);
end
