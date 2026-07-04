import React, { useRef, useEffect, useMemo, useCallback, useState } from 'react';
import ForceGraph3D, { NodeObject, LinkObject, ForceGraphMethods } from 'react-force-graph-3d';
import SpriteText from 'three-spritetext';
import { UndirectedGraph } from 'graphology';
import * as THREE from 'three';
import Legend from '@/components/graph/Legend';
import GraphLabels from '@/components/graph/GraphLabels';
import LegendButton from '@/components/graph/LegendButton';
import Settings from '@/components/graph/Settings';
import PropertiesView from '@/components/graph/PropertiesView';
import { useSettingsStore } from '@/stores/settings';
import { useGraphStore } from '@/stores/graph';
import Button from '@/components/ui/Button';
import { Network } from 'lucide-react';
import { controlButtonVariant } from '@/lib/constants';
import { useTranslation } from 'react-i18next';

interface GraphNode extends NodeObject {
  id: string;
  label?: string;
  color?: string;
  size?: number;
  type?: string;
  neighbors?: GraphNode[];
  links?: GraphLink[];
  __mesh?: THREE.Mesh; // ✅ Ссылка на 3D объект
  __originalColor?: string; // ✅ Оригинальный цвет для восстановления
}

interface GraphLink extends LinkObject {
  source: string;
  target: string;
}

interface Graph3DViewerProps {
  graph: UndirectedGraph | null;
}

const Graph3DViewer: React.FC<Graph3DViewerProps> = ({ graph }) => {
  const fgRef = useRef<ForceGraphMethods<GraphNode, GraphLink> | null>(null);
  const [clickedNode, setClickedNode] = useState<GraphNode | null>(null);
  const theme = useSettingsStore.use.theme();
  const [effectiveTheme, setEffectiveTheme] = useState(theme);
  const selectedNodeId = useGraphStore.use.selectedNode();
  const moveToSelectedNode = useGraphStore.use.moveToSelectedNode();
  const { t } = useTranslation();
  const showPropertyPanel = useSettingsStore.use.showPropertyPanel();
  const showLegend = useSettingsStore.use.showLegend();

  useEffect(() => {
    if (theme === 'system') {
      const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
      const updateTheme = () => setEffectiveTheme(mediaQuery.matches ? 'dark' : 'light');
      updateTheme();
      mediaQuery.addEventListener('change', updateTheme);
      return () => mediaQuery.removeEventListener('change', updateTheme);
    } else {
      setEffectiveTheme(theme);
    }
  }, [theme]);

  const graphData = useMemo(() => {
    if (!graph) return { nodes: [] as GraphNode[], links: [] as GraphLink[] };

    const nodes: GraphNode[] = graph.nodes().map(nodeId => ({ 
      id: nodeId, 
      ...graph.getNodeAttributes(nodeId) 
    } as GraphNode));
    
    const links: GraphLink[] = graph.edges().map(edgeId => {
      const [source, target] = graph.extremities(edgeId);
      return { source: source as string, target: target as string, ...graph.getEdgeAttributes(edgeId) };
    });

    links.forEach(link => {
      const a = nodes.find(n => n.id === link.source);
      const b = nodes.find(n => n.id === link.target);
      if (a && b) {
        (a.neighbors = a.neighbors || []).push(b);
        (b.neighbors = b.neighbors || []).push(a);
        (a.links = a.links || []).push(link);
        (b.links = b.links || []).push(link);
      }
    });

    return { nodes, links };
  }, [graph]);

  // ✅ highlightNodes объявлен ДО useCallback, которые его используют
  const { highlightNodes, highlightLinks } = useMemo(() => {
    const hNodes = new Set<GraphNode>();
    const hLinks = new Set<GraphLink>();
    const nodeToHighlight =  clickedNode;

    if (nodeToHighlight) {
      hNodes.add(nodeToHighlight);
      nodeToHighlight.neighbors?.forEach(neighbor => hNodes.add(neighbor));
      nodeToHighlight.links?.forEach(link => hLinks.add(link));
    }
    return { highlightNodes: hNodes, highlightLinks: hLinks };
  }, [clickedNode]);

  useEffect(() => {
    const node = selectedNodeId ? graphData.nodes.find(n => n.id == selectedNodeId) : null;
    setClickedNode(node || null);

    if (moveToSelectedNode && node && fgRef.current) {
      const distance = 100;
      const distRatio = 1 + distance / Math.hypot(node.x ?? 0, node.y ?? 0, node.z ?? 0);
      fgRef.current.cameraPosition(
        { 
          x: (node.x ?? 0) * distRatio, 
          y: (node.y ?? 0) * distRatio, 
          z: (node.z ?? 0) * distRatio 
        },
        { x: node.x ?? 0, y: node.y ?? 0, z: node.z ?? 0 },
        1000
      );
      useGraphStore.getState().setMoveToSelectedNode(false);
    }
  }, [selectedNodeId, moveToSelectedNode, graphData.nodes]);

  const handleNodeClick = useCallback((node: NodeObject) => {
    const graphNode = node as GraphNode;
    if (selectedNodeId === graphNode.id) {
      useGraphStore.getState().setSelectedNode(null, false);
    } else {
      useGraphStore.getState().setSelectedNode(graphNode.id, true);
    }
  }, [selectedNodeId]);

  const handleNodeHover = useCallback((node: NodeObject | null) => {
    useGraphStore.getState().setFocusedNode(node?.id as string | null);
  }, []);

  const handleBackgroundClick = useCallback(() => {
    useGraphStore.getState().setSelectedNode(null, false);
  }, []);

  const getLinkColor = useCallback((link: LinkObject) => {
    const graphLink = link as GraphLink;
    const isHighlighted = highlightLinks.has(graphLink);
    const isFaded = clickedNode !== null && !isHighlighted;
    
    if (isFaded) return 'rgba(255, 255, 255, 0.1)';
    if (isHighlighted) return 'rgb(255, 255, 255)';
    return 'rgba(255, 255, 255, 0.88)';
  }, [highlightLinks, clickedNode]);

  // ✅ Создаём mesh ОДИН раз с transparent: true
  const nodeThreeObject = useCallback((node: NodeObject) => {
    const graphNode = node as GraphNode;
    const size = Math.max((graphNode.size || 1), 5);
    const geometry = new THREE.SphereGeometry(size / 2, 16, 16);
    
    const originalColor = graphNode.color || '#ffffff';
    const material = new THREE.MeshBasicMaterial({
      color: originalColor,
      transparent: true, // ✅ Обязательно для работы opacity
      opacity: 0.75,
    });
    
    const mesh = new THREE.Mesh(geometry, material);
    
    // ✅ Сохраняем ссылки для последующего обновления
    graphNode.__mesh = mesh;
    graphNode.__originalColor = originalColor;
    
    if (graphNode.label) {
      const sprite = new SpriteText(graphNode.label);
      sprite.color = originalColor;
      sprite.textHeight = 6;
      sprite.center.y = -(graphNode.size || 2)*0.07 -0.5;
      sprite.material.transparent = true;
      sprite.material.opacity = 0.6;
      mesh.add(sprite);
      mesh.userData.labelSprite = sprite;
    }
    
    return mesh;
  }, []);

  // ✅ Обновляем материал при изменении hover/click
  useEffect(() => {
    graphData.nodes.forEach(node => {
      const mesh = node.__mesh;
      if (!mesh) return;
      
      const material = mesh.material as THREE.MeshBasicMaterial;
      const isHighlighted = highlightNodes.has(node);
      const isFaded = clickedNode !== null && !isHighlighted;
      const isMain = node === clickedNode;
      
      // ✅ Обновляем opacity
      material.opacity = isFaded ? 0.15 : (isHighlighted ? 1.0 : 0.75);
      
      // ✅ Обновляем цвет для подсветки
      if (isHighlighted) {
        material.color.set('#4488ff');
      } else {
        material.color.set(node.__originalColor || '#ffffff');
      }
      
      material.needsUpdate = true;
      
      // ✅ Обновляем opacity текста
      if (mesh.userData.labelSprite) {
        const spriteMaterial = mesh.userData.labelSprite.material;
        spriteMaterial.opacity = material.opacity;
        spriteMaterial.needsUpdate = true;
      }
    });
  }, [highlightNodes, clickedNode, graphData.nodes]);

  if (!graph) return null;

  return (
    <div className='size-full'>
      <ForceGraph3D<GraphNode, GraphLink>
        ref={fgRef as any}
        graphData={graphData}
        backgroundColor={effectiveTheme === 'dark' ? '#0c0c0d' : '#e6e6e6'}
        showPointerCursor={obj => obj ? true : false}
        nodeLabel="label"
        
        // ✅ Убираем nodeAutoColorBy — цвет управляется через nodeThreeObject
        // ✅ Убираем nodeOpacity — это глобальное число, не подходит
        
        nodeThreeObjectExtend={false} // ✅ Заменяем стандартную сферу
        nodeThreeObject={nodeThreeObject}
        
        linkColor={getLinkColor}
        linkOpacity={0.8}
        linkWidth={0.5}
        
        onNodeClick={handleNodeClick}
        onNodeHover={handleNodeHover}
        onBackgroundClick={handleBackgroundClick}
        
        // ✅ Оптимизация симуляции
        warmupTicks={50}
        cooldownTicks={100}
        cooldownTime={1000}
      />
      <div className="absolute top-2 left-2 flex items-start gap-2">
        <GraphLabels />
      </div>
      <div className="bg-background/60 absolute bottom-2 left-2 flex flex-col rounded-xl border-2 backdrop-blur-lg">
        <Button
          onClick={() => useSettingsStore.getState().setCurrentTab('knowledge-graph')}
          size="icon"
          tooltip={t("graphPanel.dimensionsSwitch2D")}
          variant={controlButtonVariant}
        >
          <Network className="h-4 w-4" />
        </Button>
        <LegendButton />
        <Settings />
      </div>
      {showPropertyPanel && (
        <div className="absolute top-2 right-2 z-10">
          <PropertiesView />
        </div>
      )}
      {showLegend && (
        <div className="absolute right-2 bottom-10 z-0">
          <Legend className="bg-background/60 backdrop-blur-lg" />
        </div>
      )}
    </div>
  );
};

export default Graph3DViewer;