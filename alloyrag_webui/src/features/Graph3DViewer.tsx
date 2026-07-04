import React from 'react';
import ForceGraph3D, { NodeObject, LinkObject } from 'react-force-graph-3d';
import SpriteText from 'three-spritetext';
import { UndirectedGraph } from 'graphology';
import * as THREE from 'three';
import Legend from '@/components/graph/Legend';
import GraphLabels from '@/components/graph/GraphLabels';
// import GraphSearch from '@/components/graph/GraphSearch';
// import { FullScreenControl, ZoomControl } from '@react-sigma/core';
import LegendButton from '@/components/graph/LegendButton';
import Settings from '@/components/graph/Settings';
import PropertiesView from '@/components/graph/PropertiesView';
import { useSettingsStore } from '@/stores/settings';
import { useGraphStore } from '@/stores/graph';

// Define custom interfaces for nodes and links by extending the base types
interface GraphNode extends NodeObject {
  id: string;
  label?: string;
  color?: string;
  size?: number;
  type?: string;
  neighbors?: GraphNode[];
  links?: GraphLink[];
}

interface GraphLink extends LinkObject {
  source: string;
  target: string;
}

interface Graph3DViewerProps {
  graph: UndirectedGraph | null;
}

const Graph3DViewer: React.FC<Graph3DViewerProps> = ({ graph }) => {
  const [hoverNode, setHoverNode] = React.useState<GraphNode | null>(null);
  const [clickedNode, setClickedNode] = React.useState<GraphNode | null>(null);
  const theme = useSettingsStore.use.theme();
  const [effectiveTheme, setEffectiveTheme] = React.useState(theme);

  React.useEffect(() => {
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

  const graphData = React.useMemo(() => {
    if (!graph) return { nodes: [] as GraphNode[], links: [] as GraphLink[] };

    const nodes: GraphNode[] = graph.nodes().map(nodeId => {
      const attrs = graph.getNodeAttributes(nodeId);
      return { id: nodeId, ...attrs } as GraphNode;
    });

    const links: GraphLink[] = graph.edges().map(edgeId => {
      const [source, target] = graph.extremities(edgeId);
      const attrs = graph.getEdgeAttributes(edgeId);
      const sourceId = source as unknown as string;
      const targetId = target as unknown as string;
      return { source: sourceId, target: targetId, ...attrs };
    });

    links.forEach(link => {
      const a = nodes.find(n => n.id === link.source);
      const b = nodes.find(n => n.id === link.target);
      if (!a || !b) return;

      a.neighbors = a.neighbors || [];
      b.neighbors = b.neighbors || [];
      a.neighbors.push(b);
      b.neighbors.push(a);

      a.links = a.links || [];
      b.links = b.links || [];
      a.links.push(link);
      b.links.push(link);
    });

    return { nodes, links };
  }, [graph]);

  const { highlightNodes, highlightLinks } = React.useMemo(() => {
    const highlightNodes = new Set<GraphNode>();
    const highlightLinks = new Set<GraphLink>();
    const nodeToHighlight: GraphNode | null = hoverNode || clickedNode;

    if (nodeToHighlight?.neighbors) {
      highlightNodes.add(nodeToHighlight);
      nodeToHighlight.neighbors.forEach(neighbor => highlightNodes.add(neighbor));
      nodeToHighlight.links?.forEach(link => highlightLinks.add(link));
    }

    return { highlightNodes, highlightLinks };
  }, [hoverNode, clickedNode]);

  const handleNodeClick = React.useCallback((node: NodeObject) => {
    const graphNode = node as GraphNode;
    if (graphNode && graphNode === clickedNode) {
      setClickedNode(null);
      useGraphStore.getState().setSelectedNode(null);
    } else {
      setClickedNode(graphNode);
      useGraphStore.getState().setSelectedNode(graphNode ? graphNode.id : null, true);
    }
    setHoverNode(null);
    useGraphStore.getState().setFocusedNode(null);
  }, [clickedNode]);

  const handleNodeHover = React.useCallback((node: NodeObject | null) => {
    setHoverNode(node as GraphNode | null);
    useGraphStore.getState().setFocusedNode(node ? node.id as string : null);
  }, []);

  const handleBackgroundClick = React.useCallback(() => {
    setClickedNode(null);
    setHoverNode(null);
    useGraphStore.getState().setSelectedNode(null);
    useGraphStore.getState().setFocusedNode(null);
  }, []);

  const showPropertyPanel = useSettingsStore.use.showPropertyPanel();
  const showLegend = useSettingsStore.use.showLegend();

  if (!graph) {
    return null;
  }

  return (
    <div className='size-full'>
      <ForceGraph3D
        graphData={graphData}
        showPointerCursor={obj => obj?true:false}
        backgroundColor={effectiveTheme === 'dark' ? '#0c0c0d' : '#e6e6e6'}
        nodeLabel="label"
        nodeAutoColorBy="type"
        nodeThreeObjectExtend={true}
        nodeThreeObject={(node) => {
          const graphNode = node as GraphNode;
          const isHighlighted = highlightNodes.has(graphNode);
          const isFaded = clickedNode !== null && !isHighlighted;

          const material = new THREE.MeshStandardMaterial({
            color: graphNode.color || 'white',
            transparent: true,
            opacity: isFaded ? 0.15 : (isHighlighted ? 1.0 : 0.75),
          });

          if (isHighlighted) {
            material.emissive = new THREE.Color('blue');
            material.emissiveIntensity = (graphNode === clickedNode || graphNode === hoverNode) ? 0.5 : 0.2;
          }

          const sphere = new THREE.Mesh(
            new THREE.SphereGeometry(Math.max((graphNode.size ?? 1) / 2, 5), 10),
            material,
          );

          sphere.castShadow = false;
          sphere.receiveShadow = false;

          if (graphNode.label) {
            const sprite = new SpriteText(graphNode.label);
            sprite.color = graphNode.color || 'white';
            sprite.textHeight = 8;
            sprite.center.y = -(graphNode.size ??10)*0.07 - 0.2;
            sprite.material.opacity = isFaded ? 0.15 : 1.0;
            sphere.add(sprite);
          }

          return sphere;
        }}
        linkColor={(link) => {
          const isFaded = clickedNode !== null && !highlightLinks.has(link as GraphLink);
          return isFaded ? 'rgba(255, 255, 255, 0.1)' : (highlightLinks.has(link as GraphLink) ? 'rgb(255, 255, 255)' : 'rgba(255, 255, 255, 0.88)');
        }}
        linkOpacity={0.6}
        linkWidth={1}
        onNodeClick={handleNodeClick}
        onNodeHover={handleNodeHover}
        onBackgroundClick={handleBackgroundClick}
      />

      <div className="absolute top-2 left-2 flex items-start gap-2">
        <GraphLabels />
        {/* Search functionality to be implemented */}
      </div>

      <div className="bg-background/60 absolute bottom-2 left-2 flex flex-col rounded-xl border-2 backdrop-blur-lg">
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
